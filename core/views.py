import logging
import random
from decimal import Decimal
from datetime import datetime, date, timedelta

from django.utils import timezone
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, Count
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.hashers import make_password

from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

import africastalking

# System models
from .models import (
    Landlord, Lease, Payment, Tenant, Property, Notice, Maintenance,
    User, RentalRequest, Meeting, PasswordResetCode
)

# Serializers
from .serializers import (
    LeaseSerializer,
    MaintenanceSerializer,
    NoticeSerializer,
    PaymentSerializer,
    PropertySerializer,
    UserRegistrationSerializer,
    UserSerializer,
    LandlordProfileSerializer,
    TenantProfileSerializer,
    LandlordCreateSerializer,
    TenantCreateSerializer,
    RentalRequestSerializer,
    MeetingSerializer
)

User = get_user_model()
logger = logging.getLogger(__name__)

# Initialize Africa's Talking SMS service
africastalking.initialize(
    username=getattr(settings, "AFRICAS_TALKING_USERNAME", "sandbox"),
    api_key=getattr(settings, "AFRICAS_TALKING_API_KEY", "")
)
sms = africastalking.SMS


# ------------------------------
# Helper functions (no new logic, just remove repetition)
# ------------------------------
def normalize_phone(phone: str) -> str:
    """Normalize Kenyan phone numbers to 254 format — no change to validation."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        return f"254{phone[1:]}"
    if phone.startswith("+"):
        return phone[1:]
    return phone

def calculate_covered_months(start_date: date, amount: Decimal, monthly_rent: Decimal, end_date: date):
    """Compute which month(s) a rent payment covers, plus any advance remainder.

    Walks forward month-by-month from the lease start date, subtracting one
    month's rent each step until the amount is exhausted or the lease ends.
    """
    covered = []
    remaining = amount
    current = start_date
    while remaining >= monthly_rent and current <= end_date:
        covered.append(current.strftime("%B %Y"))
        remaining -= monthly_rent
        # Advance to the 1st of the next month (year rollover in December).
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return covered, remaining


# ==================================================
# Admin & Landlord User Management
# ==================================================
class AdminCreateLandlordView(APIView):
    """Admin-only: creates User + linked Landlord profile in one request."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'admin':
            return Response({"error": "Only admin can create landlords."}, status=status.HTTP_403_FORBIDDEN)
        serializer = LandlordCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Landlord account created successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LandlordCreateTenantView(APIView):
    """Landlord-only: registers tenant accounts directly without public sign-up."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'landlord':
            return Response({"error": "Only landlords can register tenant accounts."}, status=status.HTTP_403_FORBIDDEN)
        if not hasattr(request.user, 'landlord_profile'):
            return Response({"error": "Landlord profile not found."}, status=status.HTTP_403_FORBIDDEN)
        serializer = TenantCreateSerializer(data=request.data, context={'request': request, 'landlord': request.user.landlord_profile})
        if serializer.is_valid():
            tenant = serializer.save()
            return Response({
                "message": "Tenant account created successfully.",
                "tenant": {
                    "id": tenant.user.id, "username": tenant.user.username,
                    "full_name": tenant.full_name, "email": tenant.user.email, "phone": tenant.phone
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================================================
# Authentication: Register, Login, Profile, Logout, Reset
# ==================================================
@api_view(["POST"])
@permission_classes([AllowAny])  # ✅ FIX: was blocking first admin creation
@transaction.atomic
def Register(request):
    """Unified registration. First user must be admin; role-based creation rules apply."""
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    requested_role = data["role"]
    user_count = User.objects.count()

    if user_count == 0 and requested_role != "admin":
        return Response({"error": "First account created must be an Admin."}, status=status.HTTP_403_FORBIDDEN)

    if user_count > 0:
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required to register new users."}, status=status.HTTP_401_UNAUTHORIZED)
        if request.user.role == "admin":
            allowed = ["admin", "landlord", "tenant"]
        elif request.user.role == "landlord":
            allowed = ["tenant"]
        else:
            return Response({"error": "You cannot create new users."}, status=status.HTTP_403_FORBIDDEN)
        if requested_role not in allowed:
            return Response({"error": f"As {request.user.role}, you can only register: {', '.join(allowed)}"}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.create_user(
            email=data["email"],
            username=data.get("username") or data["email"].split("@")[0],
            phone_number=data["phone_number"],
            password=data["password"],
            role=requested_role,
            is_staff=(requested_role == "admin"),
            is_superuser=(requested_role == "admin")
        )

        if requested_role == "landlord":
            Landlord.objects.get_or_create(user=user, defaults={
                "full_name": request.data.get("full_name", ""),
                "id_number": request.data.get("id_number", ""),
                "mpesa_number": request.data.get("mpesa_number", ""),
                "phone": request.data.get("phone", ""),
                "address": request.data.get("address", ""),
                "business_name": request.data.get("business_name", ""),
                "license_number": request.data.get("license_number", "")
            })
            p = user.landlord_profile
            for field in ["full_name", "id_number", "mpesa_number", "phone", "address", "business_name", "license_number"]:
                val = request.data.get(field)
                if val:
                    setattr(p, field, val)
            p.save()

        elif requested_role == "tenant":
            tenant_defaults = {
                "full_name": request.data.get("full_name", ""),
                "id_number": request.data.get("id_number", ""),
                "phone": request.data.get("phone", ""),
                "email_address": data["email"],
                "alternative_phone": request.data.get("alternative_phone", "")
            }
            # If a landlord is creating this tenant, track who registered them
            if request.user.is_authenticated and getattr(request.user, 'role', None) == 'landlord' and hasattr(request.user, 'landlord_profile'):
                tenant_defaults['registered_by'] = request.user.landlord_profile
            Tenant.objects.get_or_create(user=user, defaults=tenant_defaults)
            p = user.tenant
            for field in ["full_name", "id_number", "alternative_phone"]:
                val = request.data.get(field)
                if val:
                    setattr(p, field, val)
            p.save()

        return Response({
            "message": f"{requested_role.capitalize()} registered successfully",
            "user": UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

    except IntegrityError:
        return Response({"error": "Email, phone number, or ID number already exists."}, status=status.HTTP_409_CONFLICT)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def Login(request):
    """Public login. Returns JWT access/refresh tokens and profile data."""
    email = request.data.get("email")
    password = request.data.get("password")
    if not email or not password:
        return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(email=email, password=password)
    if not user:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    profile_data = {}
    if user.role == "landlord" and hasattr(user, "landlord_profile"):
        profile_data = LandlordProfileSerializer(user.landlord_profile).data
    elif user.role == "tenant" and hasattr(user, "tenant"):
        profile_data = TenantProfileSerializer(user.tenant).data
    elif user.role == "admin":
        # Admirators have their picture/name stored on the User model.
        profile_data = {
            "full_name": user.full_name or user.username,
            "phone": user.phone_number,
            "profile_picture": user.profile_picture.url if user.profile_picture else None,
        }

    return Response({
        "message": "Login successful",
        "user": UserSerializer(user).data,
        "profile": profile_data,
        "access": str(refresh.access_token),
        "refresh": str(refresh)
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Blacklists the provided refresh token."""
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"status": "success", "message": "Logged out successfully"}, status=status.HTTP_200_OK)
    except TokenError:
        return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Logout failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def send_reset_code_email(user, reset_code):
    """Send the OTP reset code to the user's email using Django's email system.

    In development (default EMAIL_BACKEND = console.EmailBackend) the email is
    printed to the server terminal, so the full flow works with ZERO external
    credentials. In production, configure SMTP via env vars (see settings.py).
    """
    from django.core.mail import send_mail
    subject = "Smart Rental System — Password Reset Code"
    message = (
        f"Hello {user.full_name or user.username},\n\n"
        f"Your password reset code is: {reset_code}\n\n"
        f"This code expires in {getattr(settings, 'PASSWORD_RESET_EXPIRE_MINUTES', 15)} minutes.\n"
        f"Do NOT share this code with anyone.\n\n"
        f"Thank you,\nSmart Rental System"
    )
    send_mail(
        subject,
        message,
        getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@smartrent.local"),
        [user.email],
        fail_silently=False,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def send_reset_code(request):
    """Sends a 6-digit reset code to the user via email OR SMS.

    Body: { email } OR { phone }. The user is looked up by whichever identifier
    is provided. If `email` is given, the code is emailed (Django's built-in
    email system). If `phone` is given, the code is sent via Africa's Talking
    SMS (requires an API key). Both are the same OTP stored in PasswordResetCode.
    """
    email = (request.data.get('email') or '').strip().lower()
    phone = (request.data.get('phone') or '').strip()

    if not email and not phone:
        return Response({"error": "Email or phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Look up user by email OR normalized phone
        user = None
        if email:
            user = User.objects.filter(email__iexact=email).first()
        if not user and phone:
            user = User.objects.filter(phone_number=normalize_phone(phone)).first()

        # Always return a generic message to avoid account enumeration.
        if not user:
            return Response({"message": "If this account is registered, a reset code was sent"}, status=status.HTTP_200_OK)

        # Invalidate any previous unused codes for this user.
        PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
        reset_code = ''.join(str(random.randint(0, 9)) for _ in range(6))
        expires_at = timezone.now() + timedelta(minutes=getattr(settings, "PASSWORD_RESET_EXPIRE_MINUTES", 15))
        PasswordResetCode.objects.create(user=user, code=reset_code, expires_at=expires_at)

        # Deliver via email if provided (alternative that needs no SMS key), else via SMS.
        if email:
            send_reset_code_email(user, reset_code)
            return Response({"status": "success", "message": "Reset code sent to your email"}, status=status.HTTP_200_OK)

        msg = f"Your Smart Rental System reset code: {reset_code}. Expires in 15 minutes. Do NOT share this code."
        sms.send(msg, [normalize_phone(phone)], sender_id=getattr(settings, "AFRICAS_TALKING_SENDER_ID", "RENTAL"))
        return Response({"status": "success", "message": "Reset code sent to your phone"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Failed to send code: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirm_password_reset(request):
    """Verifies reset code and updates password securely.

    Body: { email OR phone, code, new_password } — the user is found by whichever
    identifier they used when requesting the code.
    """
    email = (request.data.get('email') or '').strip().lower()
    phone = (request.data.get('phone') or '').strip()
    code = (request.data.get('code') or '').strip()
    new_password = request.data.get('new_password')

    if not (email or phone):
        return Response({"error": "Email or phone number is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not all([code, new_password]):
        return Response({"error": "Reset code and new password are required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(new_password) < 6:
        return Response({"error": "New password must be at least 6 characters long"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = None
        if email:
            user = User.objects.filter(email__iexact=email).first()
        if not user and phone:
            user = User.objects.filter(phone_number=normalize_phone(phone)).first()
        if not user:
            return Response({"error": "Invalid email/phone number or reset code"}, status=status.HTTP_400_BAD_REQUEST)

        reset_entry = PasswordResetCode.objects.filter(
            user=user, code=code, is_used=False, expires_at__gt=timezone.now()
        ).first()
        if not reset_entry:
            return Response({"error": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)

        user.password = make_password(new_password)
        user.save()
        reset_entry.is_used = True
        reset_entry.save()
        return Response({"status": "success", "message": "Password reset successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Password reset failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change the logged-in user's password.
    Body: { old_password, new_password }
    Verifies the current password before updating. Blacklists refresh tokens
    so the user must log in again with the new password.
    """
    user = request.user
    old_password = request.data.get("old_password") or request.data.get("current_password")
    new_password = request.data.get("new_password")

    if not old_password or not new_password:
        return Response(
            {"error": "Both current password and new password are required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    if len(new_password) < 6:
        return Response(
            {"error": "New password must be at least 6 characters long."},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not user.check_password(old_password):
        return Response(
            {"error": "Current password is incorrect."},
            status=status.HTTP_400_BAD_REQUEST
        )
    if old_password == new_password:
        return Response(
            {"error": "New password must be different from the current password."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.password = make_password(new_password)
    user.save()

    # Blacklist all refresh tokens for this user so old sessions are invalid.
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
    except Exception:
        pass

    return Response({"message": "Password changed successfully. Please log in again."}, status=status.HTTP_200_OK)


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def ProfileView(request):
    """Get or update the logged-in user's profile (landlord, tenant, or admin)."""
    user = request.user

    # Admin profiles live on the User model itself (name, phone, picture).
    if user.role == "admin":
        if request.method == "GET":
            return Response({
                "id": user.id,
                "full_name": user.full_name or user.username,
                "phone": user.phone_number,
                "phone_number": user.phone_number,
                "email": user.email,
                "profile_picture": user.profile_picture.url if user.profile_picture else None,
                "role": user.role,
            })

        # PATCH/PUT — update admin name / phone / picture.
        data = request.data
        if "full_name" in data and data.get("full_name"):
            user.full_name = data.get("full_name")
        if "phone" in data and data.get("phone"):
            user.phone_number = data.get("phone")
        if "phone_number" in data and data.get("phone_number"):
            user.phone_number = data.get("phone_number")
        # Optional multipart image upload
        pic = request.FILES.get("profile_picture")
        if pic:
            user.profile_picture = pic
        user.save()
        return Response({
            "message": "Profile updated successfully",
            "profile": {
                "id": user.id,
                "full_name": user.full_name or user.username,
                "phone": user.phone_number,
                "phone_number": user.phone_number,
                "email": user.email,
                "profile_picture": user.profile_picture.url if user.profile_picture else None,
                "role": user.role,
            },
        })

    try:
        if user.role == "landlord":
            profile = user.landlord_profile
            serializer_cls = LandlordProfileSerializer
        elif user.role == "tenant":
            profile = user.tenant
            serializer_cls = TenantProfileSerializer
        else:
            return Response({"error": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == "GET":
            return Response(serializer_cls(profile).data)

        serializer = serializer_cls(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully", "profile": serializer.data})
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    except (Landlord.DoesNotExist, Tenant.DoesNotExist):
        return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)


# ==================================================
# House-Hunting Portal (Public)
# ==================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def available_properties(request):
    """Public listing of AVAILABLE properties — no login required."""
    properties = Property.objects.filter(status='AVAILABLE').order_by('-created_at')
    return Response(PropertySerializer(properties, many=True).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_property_detail(request, property_id):
    """Public detail view for a single property — no login required."""
    try:
        prop = Property.objects.get(pk=property_id)
    except Property.DoesNotExist:
        return Response({"error": "Property not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(PropertySerializer(prop).data)


@api_view(['POST'])
@permission_classes([AllowAny])
def house_hunting_request(request):
    """
    Public rental inquiry / application — NO sign-up required.

    - Guest (anonymous): creates a RentalRequest linked to the property's landlord,
      storing applicant contact in lead_name / lead_phone / lead_email.
    - Logged-in tenant: creates a proper application linked to their tenant account.
    """
    property_id = request.data.get('property')
    if not property_id:
        return Response({"error": "property is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        prop = Property.objects.get(id=property_id)
    except (Property.DoesNotExist, ValueError):
        return Response({"error": "Property not found."}, status=status.HTTP_404_NOT_FOUND)

    if prop.status != 'AVAILABLE':
        return Response({"error": "This property is no longer available."}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user if request.user.is_authenticated else None

    # Logged-in tenant → create an application linked to their account
    if user and user.role == 'tenant' and hasattr(user, 'tenant'):
        existing = RentalRequest.objects.filter(property=prop, tenant=user.tenant).first()
        if existing:
            return Response(
                {"error": "You have already applied for this property."},
                status=status.HTTP_400_BAD_REQUEST
            )
        request_obj = RentalRequest.objects.create(
            property=prop,
            tenant=user.tenant,
            landlord=prop.landlord,
            message=request.data.get('message', '')
        )
        return Response({
            "message": "Application submitted successfully! The landlord will review your request.",
            "request": RentalRequestSerializer(request_obj).data
        }, status=status.HTTP_201_CREATED)

    # Guest / anonymous → store contact details as a lead
    lead_name = (request.data.get('lead_name') or request.data.get('full_name') or '').strip()
    lead_phone = (request.data.get('lead_phone') or request.data.get('phone') or '').strip()
    lead_email = (request.data.get('lead_email') or request.data.get('email') or '').strip()

    if not lead_name or not lead_phone:
        return Response(
            {"error": "full_name and phone are required for guest inquiries."},
            status=status.HTTP_400_BAD_REQUEST
        )

    request_obj = RentalRequest.objects.create(
        property=prop,
        landlord=prop.landlord,
        tenant=None,
        lead_name=lead_name,
        lead_phone=lead_phone,
        lead_email=lead_email,
        message=request.data.get('message', '')
    )
    return Response({
        "message": "Request submitted successfully! The landlord or admin will contact you soon.",
        "request": RentalRequestSerializer(request_obj).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def house_hunting_request_status(request):
    """
    Public guest request-status lookup — NO login required.

    Allows a guest (or any anonymous visitor) who submitted a rental inquiry
    to check the current status of their request(s) by phone number or email.

    Body: { phone: '07...', email: 'you@example.com' }  (at least one required)

    Returns a list of matches (property, status, date, landlord, notes).
    """
    phone = (request.data.get('phone') or '').strip()
    email = (request.data.get('email') or '').strip()

    if not phone and not email:
        return Response(
            {"error": "Provide your phone number or email to look up your request."},
            status=status.HTTP_400_BAD_REQUEST
        )

    qs = RentalRequest.objects.all().order_by('-created_at')

    # Filter leads by phone (normalized + raw) and/or email
    norm_phone = normalize_phone(phone) if phone else ''
    q = Q()
    if phone:
        q |= Q(lead_phone__iexact=phone) | Q(lead_phone__iexact=norm_phone) | Q(lead_phone__contains=phone.strip())
    if email:
        q |= Q(lead_email__iexact=email)
    qs = qs.filter(q)

    # Exclude requests that ended up linked to a real tenant account — those
    # users should use the normal logged-in "My Applications" tracker instead.
    qs = qs.filter(tenant__isnull=True)

    if not qs.exists():
        return Response(
            {"requests": [], "message": "No requests found for that phone or email."},
            status=status.HTTP_200_OK
        )

    return Response({
        "requests": [
            {
                "id": r.id,
                "property_title": r.property.title if r.property else None,
                "property_location": r.property.location if r.property else None,
                "status": r.status,
                "status_display": r.get_status_display(),
                "landlord_name": r.landlord.full_name if r.landlord else None,
                "landlord_notes": r.landlord_notes,
                "message": r.message,
                "created_at": r.created_at,
            }
            for r in qs
        ]
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def tenant_self_register(request):
    """Public tenant self-registration. Role is forced to 'tenant' only."""
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        user = User.objects.create_user(
            email=data["email"],
            username=data.get("username") or data["email"].split("@")[0],
            phone_number=data["phone_number"],
            password=data["password"],
            role="tenant"
        )
       
        tenant = Tenant.objects.create(
            user=user,
            full_name=request.data.get("full_name", ""),
            id_number=request.data.get("id_number", ""),
            phone=request.data.get("phone", data["phone_number"]),
            email_address=data["email"],
            alternative_phone=request.data.get("alternative_phone", "")
        )
        

        return Response({
            "message": "Tenant account created successfully — you can now browse and apply for properties",
            "user": UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)
    except IntegrityError:
        return Response({"error": "Email or phone number already exists."}, status=status.HTTP_409_CONFLICT)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==================================================
# Shared: Convert a lead request into a tenant account
# (reuses existing accounts — never creates duplicates)
# ==================================================
@transaction.atomic
def convert_lead_to_tenant_account(actor, req, landlord=None):
    """
    Convert a house-hunting rental request into a linked tenant account.

    Key principle: REUSE an existing account whenever possible — never create
    a duplicate. If an account already exists (by email, normalized phone, or
    full-name match), that exact account is granted the tenant role/privilege
    and linked to the request. A brand-new account is created ONLY as a last
    resort when nothing matches.

    actor     = authenticated User performing the action (landlord or admin)
    req       = RentalRequest instance
    landlord  = Landlord profile to mark as registered_by (None for admin)
    """
    import random
    import string

    # Already linked to a tenant → just adopt/link it.
    if req.tenant:
        profile = req.tenant
        if landlord and not profile.registered_by:
            profile.registered_by = landlord
            profile.save(update_fields=['registered_by'])
        return {
            "message": f"'{profile.full_name}' was already a tenant — now linked to your portfolio.",
            "reused_existing": True,
            "tenant": TenantProfileSerializer(profile).data,
        }

    full_name = (req.lead_name or "").strip()
    phone = (req.lead_phone or "").strip()
    email = (req.lead_email or "").strip()
    norm_phone = normalize_phone(phone)

    # 1) Try to find an existing account to reuse (email → phone → full name)
    existing_user = None
    if email:
        existing_user = User.objects.filter(email__iexact=email).first()
    if not existing_user and norm_phone:
        existing_user = User.objects.filter(phone_number=norm_phone).first()
    if not existing_user and phone:
        existing_user = User.objects.filter(phone_number=phone).first()
    if not existing_user and full_name:
        t = Tenant.objects.filter(full_name__iexact=full_name).first()
        if t:
            existing_user = t.user

    if existing_user:
        # Reuse the exact same account — attach/grant tenant privilege.
        if hasattr(existing_user, 'tenant'):
            profile = existing_user.tenant
            # Fill any missing contact details from the lead
            if not profile.full_name and full_name:
                profile.full_name = full_name
            if not profile.phone and phone:
                profile.phone = phone
            if not profile.email_address and email:
                profile.email_address = email
            profile.save()
        else:
            # Account exists but has no tenant profile (e.g. admin/landlord) —
            # attach a tenant profile to the SAME user, never a duplicate user.
            unique_id = existing_user.username
            n = 1
            while Tenant.objects.filter(id_number=unique_id).exists():
                unique_id = f"{existing_user.username}-t{n}"
                n += 1
            profile = Tenant.objects.create(
                user=existing_user,
                full_name=full_name or existing_user.get_full_name() or existing_user.username,
                id_number=unique_id,
                phone=phone or existing_user.phone_number,
                email_address=email or existing_user.email,
            )

        req.tenant = profile
        req.save(update_fields=['tenant'])

        # Grant the tenant role/privilege on the reused account
        if existing_user.role != 'tenant':
            existing_user.role = 'tenant'
            existing_user.save(update_fields=['role'])

        if landlord and not profile.registered_by:
            profile.registered_by = landlord
            profile.save(update_fields=['registered_by'])

        return {
            "message": f"Reused existing account for {profile.full_name} — same email/password still works.",
            "reused_existing": True,
            "tenant": TenantProfileSerializer(profile).data,
            "login_email": existing_user.email,
            "login_phone": existing_user.phone_number,
        }

    # 2) Last resort — no existing account found; create a brand-new one.
    generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    base_username = ''.join(filter(str.isalnum, (full_name or 'tenant').lower().split())) or f"tenant{random.randint(100, 999)}"
    username = base_username
    idx = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{idx}"
        idx += 1

    new_email = email or f"{username}@tenant.local"
    while User.objects.filter(email__iexact=new_email).exists():
        new_email = f"{username}{idx}@tenant.local"
        idx += 1

    new_phone = norm_phone or phone or f"07{random.randint(1000000, 9999999)}"
    while User.objects.filter(phone_number=new_phone).exists():
        new_phone = f"07{random.randint(1000000, 9999999)}"

    new_user = User.objects.create_user(
        email=new_email,
        username=username,
        phone_number=new_phone,
        password=generated_password,
        role="tenant",
    )

    unique_id = username
    while Tenant.objects.filter(id_number=unique_id).exists():
        unique_id = f"{username}{idx}"
        idx += 1

    profile = Tenant.objects.create(
        user=new_user,
        full_name=full_name or new_user.username,
        id_number=unique_id,
        phone=phone or new_user.phone_number,
        email_address=email or new_user.email,
    )
    if landlord:
        profile.registered_by = landlord
        profile.save(update_fields=['registered_by'])

    req.tenant = profile
    req.save(update_fields=['tenant'])

    return {
        "message": f"Tenant account created for {profile.full_name} — they can log in with their email/phone and password.",
        "reused_existing": False,
        "tenant": TenantProfileSerializer(profile).data,
        "generated_password": generated_password,
        "login_email": new_user.email,
        "login_phone": new_user.phone_number,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def admin_convert_rental_request(request, request_id):
    """Admin-only: convert any lead request into a tenant account (reuses existing)."""
    if request.user.role != 'admin':
        return Response({"error": "Admin access only."}, status=status.HTTP_403_FORBIDDEN)

    try:
        req = RentalRequest.objects.get(pk=request_id)
    except RentalRequest.DoesNotExist:
        return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

    result = convert_lead_to_tenant_account(request.user, req, landlord=None)
    return Response(result)


# ==================================================
# Rental Request Management
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def rental_request_list_create(request):
    """Submit or view rental applications. POST: tenants only. GET: role-filtered."""
    user = request.user
    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit rental requests."}, status=status.HTTP_403_FORBIDDEN)
        serializer = RentalRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            prop = serializer.validated_data['property']
            serializer.save(tenant=user.tenant, landlord=prop.landlord)
            return Response({"message": "Rental request submitted successfully", "request": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = RentalRequest.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        qs = RentalRequest.objects.filter(landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        qs = RentalRequest.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        qs = RentalRequest.objects.none()
    return Response({"rental_requests": RentalRequestSerializer(qs, many=True).data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def rental_request_detail(request, request_id):
    """View, approve/reject, or withdraw a specific rental request."""
    user = request.user
    try:
        req = RentalRequest.objects.get(id=request_id)
    except RentalRequest.DoesNotExist:
        return Response({"error": "Rental request not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'tenant' and hasattr(user, "tenant"):
        if req.tenant != user.tenant:
            return Response({"error": "You can only access your own requests."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'PUT':
            return Response({"error": "Tenants cannot edit requests."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'DELETE' and req.status != 'PENDING':
            return Response({"error": "Only pending requests can be withdrawn."}, status=status.HTTP_403_FORBIDDEN)
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        if req.landlord != user.landlord_profile:
            return Response({"error": "You can only manage your own requests."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"rental_request": RentalRequestSerializer(req).data})
    if request.method == 'PUT':
        serializer = RentalRequestSerializer(req, data=request.data, partial=True)
        if serializer.is_valid():
            new_status = serializer.validated_data.get('status', req.status)
            serializer.save()

            # When a request is APPROVED, automatically grant/link the tenant
            # account (reuse existing account; no duplicate creation).
            converted_info = None
            if new_status == 'APPROVED':
                landlord = req.landlord if req.landlord else (getattr(req.property, 'landlord', None))
                if req.property and hasattr(req.property, 'landlord'):
                    landlord = req.property.landlord
                # Only auto-convert if there's lead info to work with OR it's already linked
                if req.tenant or req.lead_name or req.lead_phone or req.lead_email:
                    converted_info = convert_lead_to_tenant_account(user, req, landlord=landlord)

            data = RentalRequestSerializer(req).data
            if converted_info:
                data['converted_tenant'] = converted_info
            return Response({"message": "Request updated successfully", "rental_request": data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        req.delete()
        return Response({"message": "Request deleted successfully."})


# ==================================================
# Meeting & Viewing Scheduling
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def meeting_list_create(request):
    """Schedule or view property viewings. Role-based filtering on GET."""
    user = request.user
    if request.method == 'POST':
        serializer = MeetingSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            prop = serializer.validated_data['property']
            if user.role == 'landlord' and hasattr(user, "landlord_profile"):
                if prop.landlord != user.landlord_profile:
                    return Response({"error": "You can only schedule for your own properties."}, status=status.HTTP_403_FORBIDDEN)
                serializer.save(landlord=user.landlord_profile)
            elif user.role == 'tenant' and hasattr(user, "tenant"):
                serializer.save(tenant=user.tenant, landlord=prop.landlord)
            else:
                return Response({"error": "Only landlords/tenants can schedule meetings."}, status=status.HTTP_403_FORBIDDEN)
            return Response({"message": "Meeting scheduled successfully", "meeting": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = Meeting.objects.all().order_by('-date_time')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        qs = Meeting.objects.filter(landlord=user.landlord_profile).order_by('-date_time')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        qs = Meeting.objects.filter(tenant=user.tenant).order_by('-date_time')
    else:
        qs = Meeting.objects.none()
    return Response({"meetings": MeetingSerializer(qs, many=True).data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def meeting_detail(request, meeting_id):
    """View, reschedule, or cancel a single meeting."""
    user = request.user
    try:
        meeting = Meeting.objects.get(id=meeting_id)
    except Meeting.DoesNotExist:
        return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'tenant' and hasattr(user, "tenant") and meeting.tenant and meeting.tenant != user.tenant:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'landlord' and hasattr(user, "landlord_profile") and meeting.landlord != user.landlord_profile:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"meeting": MeetingSerializer(meeting).data})
    if request.method == 'PUT':
        serializer = MeetingSerializer(meeting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Meeting updated successfully", "meeting": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        meeting.delete()
        return Response({"message": "Meeting cancelled successfully."})


# ==================================================
# Lease Management
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lease_list_create(request):
    """List or create leases. Auto-syncs property occupancy status."""
    user = request.user
    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins/landlords can create leases."}, status=status.HTTP_403_FORBIDDEN)
        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            prop = serializer.validated_data['property']
            if user.role == 'landlord' and prop.landlord != getattr(user, "landlord_profile", None):
                return Response({"error": "You can only create leases for your own properties."}, status=status.HTTP_403_FORBIDDEN)
            lease = serializer.save()
            if lease.status == "ACTIVE":
                prop.status = "OCCUPIED"
                prop.save(update_fields=['status'])
            return Response({"message": "Lease created successfully", "lease": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = Lease.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        qs = Lease.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        qs = Lease.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        qs = Lease.objects.none()
    return Response({"leases": LeaseSerializer(qs, many=True).data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def lease_detail(request, lease_id):
    """View, update, or delete a single lease. Syncs property occupancy."""
    user = request.user
    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        return Response({"error": "Lease not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'landlord' and hasattr(user, "landlord_profile") and lease.property.landlord != user.landlord_profile:
        return Response({"error": "You can only access your own leases."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'tenant' and hasattr(user, "tenant") and lease.tenant != user.tenant:
        return Response({"error": "You can only view your own lease."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"lease": LeaseSerializer(lease).data})
    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response({"error": "Tenants cannot edit leases."}, status=status.HTTP_403_FORBIDDEN)
        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save()
            updated.property.status = "OCCUPIED" if updated.status == "ACTIVE" else "AVAILABLE"
            updated.property.save(update_fields=['status'])
            return Response({"message": "Lease updated successfully", "lease": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins/landlords can delete leases."}, status=status.HTTP_403_FORBIDDEN)
        lease.property.status = "AVAILABLE"
        lease.property.save(update_fields=['status'])
        lease.delete()
        return Response({"message": "Lease deleted successfully."})


# ==================================================
# Notice Management
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def notice_list_create(request):
    """List or create system announcements. Only admins/landlords can create."""
    user = request.user
    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins/landlords can create notices."}, status=status.HTTP_403_FORBIDDEN)
        serializer = NoticeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=user)
            return Response({"message": "Notice created successfully", "notice": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = Notice.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        qs = Notice.objects.filter(created_by=user).order_by('-created_at')
    elif user.role == 'tenant':
        qs = Notice.objects.filter(Q(target='ALL') | Q(target='ALL TENANTS')).order_by('-created_at')
    else:
        qs = Notice.objects.none()
    return Response({"notices": NoticeSerializer(qs, many=True).data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def notice_detail(request, notice_id):
    """Manage a single notice. Tenants can only view."""
    user = request.user
    try:
        notice = Notice.objects.get(id=notice_id)
    except Notice.DoesNotExist:
        return Response({"error": "Notice not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'tenant' and request.method != 'GET':
        return Response({"error": "Tenants cannot modify notices."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'landlord' and notice.created_by != user:
        return Response({"error": "You can only manage your own notices."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"notice": NoticeSerializer(notice).data})
    if request.method == 'PUT':
        serializer = NoticeSerializer(notice, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Notice updated successfully", "notice": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        notice.delete()
        return Response({"message": "Notice deleted successfully."})


# ==================================================
# Maintenance Requests
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def maintenance_list_create(request):
    """List or submit maintenance requests. Only tenants can submit."""
    user = request.user
    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit maintenance requests."}, status=status.HTTP_403_FORBIDDEN)
        serializer = MaintenanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=user.tenant)
            return Response({"message": "Maintenance request submitted successfully", "maintenance": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = Maintenance.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        qs = Maintenance.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        qs = Maintenance.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        qs = Maintenance.objects.none()
    return Response({"maintenance_requests": MaintenanceSerializer(qs, many=True).data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def maintenance_detail(request, maintenance_id):
    """View, update, or delete a single maintenance request."""
    user = request.user
    try:
        req = Maintenance.objects.get(id=maintenance_id)
    except Maintenance.DoesNotExist:
        return Response({"error": "Maintenance request not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'tenant':
        if req.tenant != user.tenant:
            return Response({"error": "You can only access your own requests."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'DELETE':
            return Response({"error": "Tenants cannot delete requests."}, status=status.HTTP_403_FORBIDDEN)
    elif user.role == 'landlord' and hasattr(user, "landlord_profile") and req.property.landlord != user.landlord_profile:
        return Response({"error": "You can only manage your own requests."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"maintenance": MaintenanceSerializer(req).data})
    if request.method == 'PUT':
        serializer = MaintenanceSerializer(req, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Maintenance request updated successfully", "maintenance": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins/landlords can delete requests."}, status=status.HTTP_403_FORBIDDEN)
        req.delete()
        return Response({"message": "Maintenance request deleted successfully."})


# ==================================================
# Payments
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def payment_list_create(request):
    """Submit payments or view history. Includes summary stats."""
    user = request.user
    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit payments."}, status=status.HTTP_403_FORBIDDEN)
        serializer = PaymentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            lease = serializer.validated_data['lease']
            if lease.tenant_id != user.tenant.id:
                return Response({"error": "Not your lease."}, status=status.HTTP_403_FORBIDDEN)
            if lease.status != "ACTIVE":
                return Response({"error": "Can only pay for active leases."}, status=status.HTTP_400_BAD_REQUEST)
            if lease.end_date < timezone.now().date():  # ✅ FIX: timezone-aware
                return Response({"error": "Lease has expired."}, status=status.HTTP_400_BAD_REQUEST)

            payment = serializer.save()
            monthly_rent = Decimal(lease.monthly_rent)
            paid = Decimal(payment.amount)
            covered, remaining = calculate_covered_months(lease.start_date, paid, monthly_rent, lease.end_date)
            payment.covered_months = covered
            payment.save(update_fields=['covered_months'])

            total_done = lease.payments.filter(status='COMPLETED').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            new_bal = max(Decimal('0'), lease.monthly_rent - (total_done + paid))
            txt = ", ".join(covered) if covered else ""
            note = f" plus KSh {remaining:.2f} advance" if remaining > 0 else ""
            msg = f"Payment submitted! Covers: {txt}{note}. Awaiting verification." if covered else "Payment submitted, awaiting verification."

            return Response({
                "message": msg, "amount_paid": f"{paid:.2f}",
                "covers_months": covered,
                "advance_credit_remaining": f"{remaining:.2f}" if remaining > 0 else "0.00",
                "remaining_balance_due": f"{new_bal:.2f}",
                "payment": PaymentSerializer(payment, context={'request': request}).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if user.role == 'admin':
        qs = Payment.objects.all().select_related('lease', 'lease__tenant', 'lease__property')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        qs = Payment.objects.filter(lease__property__landlord=user.landlord_profile).select_related('lease', 'lease__tenant', 'lease__property')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        qs = Payment.objects.filter(lease__tenant=user.tenant).select_related('lease', 'lease__tenant', 'lease__property')
    else:
        qs = Payment.objects.none()

    s, lid, tid = request.query_params.get('status'), request.query_params.get('lease_id'), request.query_params.get('tenant_id')
    if s:
        qs = qs.filter(status=s.upper())
    if lid:
        qs = qs.filter(lease_id=lid)
    if tid and user.role in ['admin', 'landlord']:
        qs = qs.filter(lease__tenant_id=tid)

    # Compute aggregates via SQL — never sum full model objects in Python.
    totals = qs.aggregate(
        total_paid=Sum('amount', filter=Q(status='COMPLETED')),
        total_pending=Sum('amount', filter=Q(status='PENDING')),
    )
    total_paid = totals['total_paid'] or Decimal('0.00')
    total_pending = totals['total_pending'] or Decimal('0.00')
    mr = qs.first().lease.monthly_rent if qs.exists() else Decimal('0.00')
    bal = max(Decimal('0.00'), mr - total_paid)
    cm = f"Owe KSh {bal:.2f}. Clear before paying new months." if bal > 0 else "All up to date!"

    return Response({
        "summary": {
            "monthly_rent": f"{mr:.2f}",
            "total_paid": f"{total_paid:.2f}",
            "total_pending": f"{total_pending:.2f}",
            "balance_due": f"{bal:.2f}",
            "clear_message": cm,
            "note": "Payments apply oldest first."
        },
        "payments": PaymentSerializer(qs.order_by('-created_at'), many=True, context={'request': request}).data
    })


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    """View, update, or delete a single payment. Tenants can only view."""
    try:
        payment = Payment.objects.select_related('lease', 'lease__property', 'lease__tenant').get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    u = request.user
    if u.role == 'tenant' and hasattr(u, "tenant") and payment.lease.tenant != u.tenant:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
    if u.role == 'tenant' and request.method in ['PUT', 'DELETE']:
        return Response({"error": "Only landlords/admins can modify payments."}, status=status.HTTP_403_FORBIDDEN)
    if u.role == 'landlord' and hasattr(u, "landlord_profile") and payment.lease.property.landlord != u.landlord_profile:
        return Response({"error": "Not your property."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"payment": PaymentSerializer(payment, context={'request': request}).data})
    if request.method == 'PUT':
        s = PaymentSerializer(payment, data=request.data, partial=True, context={'request': request})
        if s.is_valid():
            s.save()
            return Response({"message": "Payment updated.", "payment": s.data})
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        if u.role != 'admin':
            return Response({"error": "Only admins can delete payments."}, status=status.HTTP_403_FORBIDDEN)
        payment.delete()
        return Response({"message": "Payment deleted."})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rent_for_month(request):
    """Check rent status for a month: ?lease_id=1&month=2026-07"""
    month, lease_id = request.query_params.get('month'), request.query_params.get('lease_id')
    if not month:
        return Response({"error": "?month=YYYY-MM required"}, status=status.HTTP_400_BAD_REQUEST)
    if not lease_id:
        return Response({"error": "?lease_id=N required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        target = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        return Response({"error": "Invalid date. Use YYYY-MM"}, status=status.HTTP_400_BAD_REQUEST)

    if request.user.role != 'tenant' or not hasattr(request.user, "tenant"):
        return Response({"error": "Only tenants can check."}, status=status.HTTP_403_FORBIDDEN)

    try:
        lease = Lease.objects.get(id=lease_id, tenant=request.user.tenant, status='ACTIVE')
    except Lease.DoesNotExist:
        return Response({"error": "Active lease not found."}, status=status.HTTP_404_NOT_FOUND)

    if target < lease.start_date or target > lease.end_date:
        return Response({"error": f"Lease: {lease.start_date} to {lease.end_date}"}, status=status.HTTP_400_BAD_REQUEST)

    total = lease.payments.filter(status='COMPLETED').aggregate(Sum('amount'))['total'] or Decimal('0.00')
    paid = total >= lease.monthly_rent
    return Response({
        "month": target.strftime("%B %Y"),
        "lease_id": lease.id,
        "property": lease.property.title,
        "monthly_rent": float(lease.monthly_rent),
        "total_paid": float(total),
        "status": "PAID" if paid else "PAYABLE",
        "amount_due": float(Decimal('0.00') if paid else lease.monthly_rent - total)
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def verify_payment(request, payment_id):
    """Landlord/admin: verifies a pending payment (COMPLETED/FAILED)."""
    try:
        payment = Payment.objects.select_related('lease', 'lease__property', 'lease__tenant').get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

    u = request.user
    if u.role == 'tenant':
        return Response({"error": "Only landlords/admins can verify."}, status=status.HTTP_403_FORBIDDEN)
    if u.role == 'landlord' and hasattr(u, 'landlord_profile') and payment.lease.property.landlord != u.landlord_profile:
        return Response({"error": "Not your property."}, status=status.HTTP_403_FORBIDDEN)
    if payment.status != 'PENDING':
        return Response({"error": "Only pending payments."}, status=status.HTTP_400_BAD_REQUEST)
    ns = request.data.get('status')
    if ns not in ['COMPLETED', 'FAILED']:
        return Response({"error": "Must be COMPLETED/FAILED."}, status=status.HTTP_400_BAD_REQUEST)

    if ns == 'COMPLETED':
        lease = payment.lease
        mr, amt = Decimal(lease.monthly_rent), Decimal(payment.amount)
        covered, remaining = calculate_covered_months(lease.start_date, amt, mr, lease.end_date)
        payment.status = 'COMPLETED'
        payment.receipt_number = f"RCP-{payment.id}-{int(timezone.now().timestamp())}"
        payment.receipt_issued_at = timezone.now()
        payment.covered_months = covered
        payment.balance_after_payment = remaining
        # Set issuer: explicit input first, else the LANDLORD's name (the official
        # issuer of the receipt), else the logged-in user's name, else username.
        # The landlord is the owner of the property linked to this lease.
        landlord_name = None
        try:
            landlord_name = lease.property.landlord.full_name or lease.property.landlord.business_name
        except Exception:
            landlord_name = None
        payment.issued_by = request.data.get('issued_by') or (
            landlord_name or
            getattr(u, 'full_name', None) or
            (u.landlord_profile.full_name if hasattr(u, 'landlord_profile') and u.landlord_profile.full_name else None) or
            u.username
        )
        payment.save()
        return Response({
            "message": "Verified",
            "receipt_number": payment.receipt_number,
            "covers_months": covered,
            "balance_remaining": f"{remaining:.2f}",
            "payment": PaymentSerializer(payment).data
        })

    payment.status = 'FAILED'
    payment.save()
    return Response({"message": "Marked as failed", "payment": PaymentSerializer(payment).data})


# ==================================================
# M-Pesa STK Push
# ==================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mpesa_stk_push(request):
    """Initiate M-Pesa STK Push — tenant receives PIN prompt on phone."""
    from .mpesa import MpesaService

    u = request.user
    if u.role != 'tenant' or not hasattr(u, 'tenant'):
        return Response({"error": "Only tenants can use M-Pesa."}, status=status.HTTP_403_FORBIDDEN)

    lease_id = request.data.get('lease_id')
    amount = request.data.get('amount')
    phone = request.data.get('phone') or u.phone_number
    if not lease_id or not amount:
        return Response({"error": "lease_id and amount required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lease = Lease.objects.get(id=lease_id, tenant=u.tenant, status='ACTIVE')
    except Lease.DoesNotExist:
        return Response({"error": "Active lease not found."}, status=status.HTTP_404_NOT_FOUND)
    if lease.end_date < timezone.now().date():  # ✅ FIX: timezone-aware
        return Response({"error": "Lease expired."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        mpesa = MpesaService()
        result = mpesa.stk_push(
            phone=phone,
            amount=amount,
            account_ref=f"LEASE-{lease.id}",
            description=f"Rent for {lease.property.title}"
        )
    except Exception as e:
        return Response({"error": f"M-Pesa failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    if result.get('ResponseCode') != '0':
        return Response({
            "error": result.get('errorMessage', 'STK push failed'),
            "mpesa_response": result
        }, status=status.HTTP_400_BAD_REQUEST)

    payment = Payment.objects.create(
        lease=lease,
        amount=amount,
        method='M-Pesa',
        status='PENDING',
        mpesa_checkout_request_id=result.get('CheckoutRequestID')
    )
    return Response({
        "message": "STK Push sent. Enter M-Pesa PIN.",
        "payment_id": payment.id,
        "checkout_request_id": result.get('CheckoutRequestID'),
        "mpesa_response": result
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_callback(request):
    """Safaricom callback — receives STK result and updates payment status.

    NOTE: Safaricom callbacks cannot carry a JWT. For production, protect this
    endpoint by:
      - verifying the request comes from Safaricom's IP ranges (via the proxy /
        firewall), and/or
      - using the C2B/STK confirmation endpoints offered by Safaricom that
        include an initiator password.
    A forged callback can only mark a PENDING payment as COMPLETED/FAILED —
    it cannot create money, but you should still gate this endpoint in prod.
    """
    data = request.data
    stk = data.get('Body', {}).get('stkCallback', {})
    cid = stk.get('CheckoutRequestID')
    rc = stk.get('ResultCode')
    if not cid:
        # Malformed callback — log it instead of silently acking.
        logger.warning("M-Pesa callback with missing CheckoutRequestID: %s", data)
        return Response({"received": True})

    # ResultCode must be present; Safaricom sends an integer.
    if rc is None:
        logger.warning("M-Pesa callback missing ResultCode for %s", cid)
        return Response({"received": True})

    try:
        payment = Payment.objects.get(mpesa_checkout_request_id=cid)
    except Payment.DoesNotExist:
        return Response({"received": True})

    if rc == 0:
        items = stk.get('CallbackMetadata', {}).get('Item', [])
        ref = next((i['Value'] for i in items if i.get('Name') == 'MpesaReceiptNumber'), None)
        payment.status = 'COMPLETED'
        payment.transaction_id = ref
        payment.receipt_issued_at = timezone.now()
        payment.receipt_number = f"RCP-{payment.id}-{int(timezone.now().timestamp())}"

        lease = payment.lease
        mr = Decimal(lease.monthly_rent)
        amt = Decimal(payment.amount)
        covered, remaining = calculate_covered_months(lease.start_date, amt, mr, lease.end_date)
        payment.covered_months = covered
        payment.balance_after_payment = remaining
        # Explicitly set the issuer so the receipt always shows WHO issued it.
        # The LANDLORD is the official issuer of the receipt — never the tenant.
        if not payment.issued_by:
            try:
                landlord = lease.property.landlord if lease and lease.property else None
                payment.issued_by = (landlord.full_name or landlord.business_name or 'M-Pesa') if landlord else 'M-Pesa'
            except Exception:
                payment.issued_by = 'M-Pesa'
        payment.full_clean()
        payment.save(update_fields=[
            'status', 'transaction_id', 'receipt_issued_at', 'receipt_number',
            'covered_months', 'balance_after_payment', 'issued_by'
        ])

        try:
            t = lease.tenant
            p = normalize_phone(t.phone)
            mt = ', '.join(covered) if covered else 'N/A'
            sms.send(
                (
                    f"Rent Confirmed!\n"
                    f"Receipt: {payment.receipt_number}\n"
                    f"KSh {payment.amount}\n"
                    f"Ref: {ref}\n"
                    f"Covers: {mt}\n"
                    f"Property: {lease.property.title}"
                ),
                [p],
                sender_id=getattr(settings, 'AFRICAS_TALKING_SENDER_ID', 'RENTAL')
            )
        except Exception:
            pass
    else:
        payment.status = 'FAILED'
        payment.save(update_fields=['status'])
    return Response({"received": True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_receipt(request, payment_id):
    """Fetch a completed payment receipt."""
    try:
        payment = Payment.objects.select_related('lease', 'lease__property', 'lease__tenant').get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    u = request.user
    if u.role == 'tenant' and hasattr(u, 'tenant') and payment.lease.tenant != u.tenant:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
    if u.role == 'landlord' and hasattr(u, 'landlord_profile') and payment.lease.property.landlord != u.landlord_profile:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
    if payment.status != 'COMPLETED':
        return Response({"error": "Only completed payments have receipts."}, status=status.HTTP_400_BAD_REQUEST)

    l = payment.lease
    return Response({
        "receipt": {
            "receipt_number": payment.receipt_number,
            "issued_at": payment.receipt_issued_at,
            "issued_by": payment.issued_by,
            "tenant": l.tenant.full_name,
            "property": l.property.title,
            "amount_paid": f"{payment.amount:.2f}",
            "mpesa_ref": payment.transaction_id,
            "method": payment.method,
            "covers_months": payment.covered_months,
            "balance_after": f"{payment.balance_after_payment:.2f}" if payment.balance_after_payment else "0.00",
            "payment_id": payment.id
        }
    })
# ==================================================
# Admin Dashboard
# ==================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard_stats(request):
    """System-wide stats. Admin only."""
    if request.user.role != 'admin':
        return Response({"error": "Admin only."}, status=status.HTTP_403_FORBIDDEN)

    total_properties = Property.objects.count()
    total_landlords = Landlord.objects.count()
    total_tenants = Tenant.objects.count()
    active_leases = Lease.objects.filter(status="ACTIVE").count()
    occupied = Property.objects.filter(status="OCCUPIED").count()
    vacant = Property.objects.filter(status="AVAILABLE").count()
    occupancy_rate = round((occupied / total_properties * 100) if total_properties else 0, 2)
    total_collected = Payment.objects.filter(status="COMPLETED").aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_pending = Payment.objects.filter(status="PENDING").aggregate(t=Sum('amount'))['t'] or Decimal('0')
    pending_maintenance = Maintenance.objects.filter(status__in=["PENDING", "IN_PROGRESS"]).count()
    pending_requests = RentalRequest.objects.filter(status="PENDING").count()

    return Response({
        "overview": {
            "total_properties": total_properties,
            "total_landlords": total_landlords,
            "total_tenants": total_tenants,
            "active_leases": active_leases,
            "occupancy_rate_percent": occupancy_rate
        },
        "properties": {
            "occupied": occupied,
            "vacant": vacant
        },
        "payments": {
            "total_collected": float(total_collected),
            "total_pending": float(total_pending)
        },
        "pending_actions": {
            "maintenance": pending_maintenance,
            "rental_requests": pending_requests
        }
    })


def _paginate_queryset(qs, request, default_page_size=50, max_page_size=200):
    """
    Lightweight limit/offset pagination helper.

    Reads `?page=N` (1-based) and `?page_size=M` (or `?limit=` / `?offset=`)
    from the request query params. Returns (page_qs, meta_dict).
    """
    try:
        page_size = int(request.query_params.get('page_size', request.query_params.get('limit', default_page_size)))
    except (TypeError, ValueError):
        page_size = default_page_size
    page_size = max(1, min(page_size, max_page_size))

    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    page_qs = qs[start:end]

    meta = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }
    return page_qs, meta


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_users(request):
    """Returns paginated list of all system users. Admin only."""
    if request.user.role != 'admin':
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    users_qs = User.objects.all().order_by('-date_joined')
    users_qs, meta = _paginate_queryset(users_qs, request)
    users = list(users_qs)

    data = [{
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "role": u.role,
        "phone_number": u.phone_number,
        "is_active": u.is_active,
        "date_joined": u.date_joined,
        "full_name": u.full_name or
            (u.landlord_profile.full_name if hasattr(u, 'landlord_profile') and u.landlord_profile.full_name else None) or
            (u.tenant.full_name if hasattr(u, 'tenant') and u.tenant.full_name else None) or
            u.username,
        "profile_picture": u.profile_picture.url if u.profile_picture else None,
    } for u in users]

    return Response({"users": data, "meta": meta})

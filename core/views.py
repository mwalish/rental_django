# ==================================================
# Imports — Core libraries, DRF utilities, models & serializers
# ==================================================
"""
Views module for the core property management system.
All endpoints follow consistent role-based access control rules.
Changes here affect API behavior — test thoroughly after updates.
"""
import random
from decimal import Decimal
from datetime import datetime, date, timedelta

from django.utils import timezone
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, Count
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.hashers import make_password

from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView 
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

import africastalking

# System models — keep imports synced with models.py
from .models import (
    Landlord, Lease, Payment, Tenant, Property, Notice, Maintenance,
    User, RentalRequest, Meeting, PasswordResetCode
)

# Serializers for data conversion & validation — synced with serializers.py
from .serializers import (
    LeaseSerializer,
    MaintenanceSerializer,
    NoticeSerializer,
    PaymentSerializer,
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

# Initialize Africa's Talking SMS service
africastalking.initialize(
    username=getattr(settings, "AFRICAS_TALKING_USERNAME", "sandbox"),
    api_key=getattr(settings, "AFRICAS_TALKING_API_KEY", "")
)
sms = africastalking.SMS


# ==================================================
# Admin & Landlord User Management
# ==================================================
class AdminCreateLandlordView(APIView):
    """
    Admin-only endpoint to create new landlord accounts.
    Automatically creates both core User record and linked Landlord profile.
    Permissions: Must be logged in as system admin.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Block non-admin users from accessing this endpoint
        if request.user.role != 'admin':
            return Response({"error": "Only admin can create landlords."}, status=status.HTTP_403_FORBIDDEN)

        # Validate input data against serializer rules
        serializer = LandlordCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Landlord account created successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LandlordCreateTenantView(APIView):
    """
    Landlord-only endpoint to register new tenant accounts directly.
    Used when landlords add tenants to their properties without public sign-up.
    Permissions: Must be logged in as landlord.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Block non-landlord users clearly
        if request.user.role != 'landlord':
            return Response(
                {"error": "Only landlords can register tenant accounts."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TenantCreateSerializer(data=request.data)
        if serializer.is_valid():
            tenant = serializer.save()
            return Response({
                "message": "Tenant account created successfully.",
                "tenant": {
                    "id": tenant.user.id,
                    "username": tenant.user.username,
                    "full_name": tenant.full_name,
                    "email": tenant.user.email,
                    "phone": tenant.phone
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================================================
# Authentication: Register, Login, Profile, Logout, Reset
# ==================================================
@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def Register(request):
    """
    Unified user registration endpoint.
    - First account ever created MUST be an admin
    - Admins can create admin/landlord/tenant accounts
    - Landlords can only create tenant accounts
    - Automatically creates matching Landlord/Tenant profile on success
    - Uses atomic transaction to avoid partial creation if anything fails
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    requested_role = data["role"]
    user_count = User.objects.count()

    # Enforce system setup rule: first user is always admin
    if user_count == 0 and requested_role != "admin":
        return Response({"error": "First account created must be an Admin."}, status=status.HTTP_403_FORBIDDEN)

    # Enforce role-based creation limits for existing systems
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
        # Create core user account with correct permissions
        user = User.objects.create_user(
            email=data["email"],
            username=data.get("username") or data["email"].split("@")[0],
            phone_number=data["phone_number"],
            password=data["password"],
            role=requested_role,
            is_staff=(requested_role == "admin"),
            is_superuser=(requested_role == "admin")
        )

        # Create and populate linked Landlord profile
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
            profile = user.landlord_profile
            profile.full_name = request.data.get("full_name", profile.full_name)
            profile.id_number = request.data.get("id_number", profile.id_number)
            profile.mpesa_number = request.data.get("mpesa_number", profile.mpesa_number)
            profile.address = request.data.get("address", profile.address)
            profile.business_name = request.data.get("business_name", profile.business_name)
            profile.license_number = request.data.get("license_number", profile.license_number)
            profile.save()

        # Create and populate linked Tenant profile
        elif requested_role == "tenant":
            Tenant.objects.get_or_create(user=user, defaults={
                "full_name": request.data.get("full_name", ""),
                "id_number": request.data.get("id_number", ""),
                "phone": request.data.get("phone", ""),
                "email_address": data["email"],
                "alternative_phone": request.data.get("alternative_phone", "")
            })
            profile = user.tenant
            profile.full_name = request.data.get("full_name", profile.full_name)
            profile.id_number = request.data.get("id_number", profile.id_number)
            profile.alternative_phone = request.data.get("alternative_phone", profile.alternative_phone)
            profile.save()

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
    """
    Public login endpoint.
    Accepts email + password, returns JWT access/refresh tokens.
    Also includes full profile data for the logged-in user's role.
    Tokens are used for all authenticated requests.
    """
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=email, password=password)
    if not user:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    profile_data = {}

    # Attach role-specific profile data to response
    if user.role == "landlord" and hasattr(user, "landlord_profile"):
        profile_data = LandlordProfileSerializer(user.landlord_profile).data
    elif user.role == "tenant" and hasattr(user, "tenant"):
        profile_data = TenantProfileSerializer(user.tenant).data

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
    """
    Secure JWT Logout endpoint.
    Invalidates/blacklists the provided refresh token so it cannot be reused.
    Requires valid access token in headers and refresh token in request body.
    """
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Blacklist the refresh token permanently
        token = RefreshToken(refresh_token)
        token.blacklist()

        return Response(
            {"status": "success", "message": "Logged out successfully"},
            status=status.HTTP_200_OK
        )

    except TokenError:
        return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Logout failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def send_reset_code(request):
    """
    Send 6-digit password reset code via SMS to user's registered phone number.
    Normalizes Kenyan phone numbers to 254 format automatically.
    Does NOT confirm if number exists — prevents leaking registered accounts.
    Invalidates all old unused codes for the same user before creating new one.
    """
    phone = request.data.get('phone')

    if not phone:
        return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Normalize phone to standard Kenyan format 254xxxxxxxxx
    if phone.startswith("0"):
        phone = f"254{phone[1:]}"
    elif phone.startswith("+"):
        phone = phone[1:]

    try:
        # Match against custom User phone_number field
        user = User.objects.filter(phone_number=phone).first()
        if not user:
            # Return identical message whether found or not for security
            return Response(
                {"message": "If this number is registered, a reset code was sent"},
                status=status.HTTP_200_OK
            )

        # Mark all old unused codes as used
        PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)

        # Generate new 6-digit numeric code
        reset_code = ''.join(str(random.randint(0, 9)) for _ in range(6))
        expires_at = timezone.now() + timedelta(minutes=getattr(settings, "PASSWORD_RESET_EXPIRE_MINUTES", 15))

        # Save new reset code to database
        PasswordResetCode.objects.create(
            user=user,
            code=reset_code,
            expires_at=expires_at
        )

        # Send SMS via Africa's Talking gateway
        message = f"Your Smart Rental System reset code: {reset_code}. Expires in 15 minutes. Do NOT share this code with anyone."
        sms.send(message, [phone], sender_id=getattr(settings, "AFRICAS_TALKING_SENDER_ID", "RENTAL"))

        return Response(
            {"status": "success", "message": "Reset code sent to your phone"},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        return Response({"error": f"Failed to send code: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirm_password_reset(request):
    """
    Verify reset code and update user password securely.
    Checks that code is correct, not expired, and not already used.
    Password is hashed automatically before saving to database.
    Code is marked as used immediately after success — cannot be reused.
    """
    phone = request.data.get('phone')
    code = request.data.get('code')
    new_password = request.data.get('new_password')

    if not all([phone, code, new_password]):
        return Response(
            {"error": "Phone number, reset code, and new password are all required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 6:
        return Response({"error": "New password must be at least 6 characters long"}, status=status.HTTP_400_BAD_REQUEST)

    # Normalize phone number again for matching
    if phone.startswith("0"):
        phone = f"254{phone[1:]}"
    elif phone.startswith("+"):
        phone = phone[1:]

    try:
        user = User.objects.filter(phone_number=phone).first()
        if not user:
            return Response({"error": "Invalid phone number or reset code"}, status=status.HTTP_400_BAD_REQUEST)

        # Find valid, unused, non-expired reset code
        reset_entry = PasswordResetCode.objects.filter(
            user=user,
            code=code,
            is_used=False,
            expires_at__gt=timezone.now()
        ).first()

        if not reset_entry:
            return Response({"error": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)

        # Update password securely
        user.password = make_password(new_password)
        user.save()

        # Mark code as used permanently
        reset_entry.is_used = True
        reset_entry.save()

        return Response(
            {"status": "success", "message": "Password reset successfully — you can now login with your new password"},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        return Response({"error": f"Password reset failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def ProfileView(request):
    """
    Get or update the logged-in user's own profile.
    - Admins do not have a separate profile record
    - Supports full update (PUT) or partial update (PATCH)
    - Users can only edit their own profile
    """
    user = request.user

    if user.role == "admin":
        return Response({"message": "Admin users do not have a separate profile."})

    try:
        if user.role == "landlord":
            if not hasattr(user, "landlord_profile"):
                return Response({"error": "Landlord profile not found."}, status=status.HTTP_404_NOT_FOUND)
            profile = user.landlord_profile
            serializer_cls = LandlordProfileSerializer

        elif user.role == "tenant":
            if not hasattr(user, "tenant"):
                return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)
            profile = user.tenant
            serializer_cls = TenantProfileSerializer

        else:
            return Response({"error": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == "GET":
            serializer = serializer_cls(profile)
        else:
            serializer = serializer_cls(profile, data=request.data, partial=True)

    except (Landlord.DoesNotExist, Tenant.DoesNotExist):
        return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(serializer.data)

    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Profile updated successfully", "profile": serializer.data})
    
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# ==================================================
# Rental Request Management
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def rental_request_list_create(request):
    """
    Submit or view rental applications for properties.
    - POST: Tenants only; auto-links request to property's landlord; blocks duplicate pending requests
    - GET: Tenants see their own requests; landlords see requests for their properties; admins see all
    """
    user = request.user

    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit rental requests."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RentalRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Auto-set tenant and landlord from selected property
            property_obj = serializer.validated_data['property']
            serializer.save(tenant=user.tenant, landlord=property_obj.landlord)
            return Response({"message": "Rental request submitted successfully", "request": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter requests based on user role
    if user.role == 'admin':
        requests = RentalRequest.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        requests = RentalRequest.objects.filter(landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        requests = RentalRequest.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        requests = RentalRequest.objects.none()

    serializer = RentalRequestSerializer(requests, many=True)
    return Response({"rental_requests": serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def rental_request_detail(request, request_id):
    """
    View, update, or delete a specific rental request.
    - Landlords can approve/reject and add notes
    - Tenants can only view or withdraw their own pending requests
    """
    user = request.user

    try:
        req = RentalRequest.objects.get(id=request_id)
    except RentalRequest.DoesNotExist:
        return Response({"error": "Rental request not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access control checks
    if user.role == 'tenant' and hasattr(user, "tenant"):
        if req.tenant != user.tenant:
            return Response({"error": "You can only access your own rental requests."}, status=status.HTTP_403_FORBIDDEN)
        # Tenants can only delete pending requests
        if request.method == 'PUT':
            return Response({"error": "Tenants cannot edit requests — only landlords can approve/reject."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'DELETE' and req.status != 'PENDING':
            return Response({"error": "Only pending requests can be withdrawn."}, status=status.HTTP_403_FORBIDDEN)

    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        if req.landlord != user.landlord_profile:
            return Response({"error": "You can only manage requests for your own properties."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = RentalRequestSerializer(req)
        return Response({"rental_request": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = RentalRequestSerializer(req, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Request updated successfully", "rental_request": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        req.delete()
        return Response({"message": "Request deleted successfully."}, status=status.HTTP_200_OK)


# ==================================================
# Meeting & Viewing Scheduling
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def meeting_list_create(request):
    """
    Schedule or view property meetings/viewings.
    - POST: Landlords can schedule for any tenant; tenants can only schedule for themselves
    - Supports viewings for new applicants or meetings for existing tenants
    """
    user = request.user

    if request.method == 'POST':
        serializer = MeetingSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']
            # Auto-set landlord from property
            if user.role == 'landlord' and hasattr(user, "landlord_profile"):
                if property_obj.landlord != user.landlord_profile:
                    return Response({"error": "You can only schedule meetings for your own properties."}, status=status.HTTP_403_FORBIDDEN)
                serializer.save(landlord=user.landlord_profile)
            elif user.role == 'tenant' and hasattr(user, "tenant"):
                serializer.save(tenant=user.tenant, landlord=property_obj.landlord)
            else:
                return Response({"error": "Only landlords and tenants can schedule meetings."}, status=status.HTTP_403_FORBIDDEN)

            return Response({"message": "Meeting scheduled successfully", "meeting": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter meetings based on role
    if user.role == 'admin':
        meetings = Meeting.objects.all().order_by('-date_time')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        meetings = Meeting.objects.filter(landlord=user.landlord_profile).order_by('-date_time')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        meetings = Meeting.objects.filter(Q(tenant=user.tenant) | Q(tenant__isnull=True, property__landlord__isnull=False)).order_by('-date_time')
    else:
        meetings = Meeting.objects.none()

    serializer = MeetingSerializer(meetings, many=True)
    return Response({"meetings": serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def meeting_detail(request, meeting_id):
    """
    View, reschedule, or cancel a single meeting.
    - Tenants can only view or cancel their own meetings
    - Landlords can edit/cancel meetings for their properties
    """
    user = request.user

    try:
        meeting = Meeting.objects.get(id=meeting_id)
    except Meeting.DoesNotExist:
        return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access rules
    if user.role == 'tenant' and hasattr(user, "tenant"):
        if meeting.tenant and meeting.tenant != user.tenant:
            return Response({"error": "You can only access meetings you are part of."}, status=status.HTTP_403_FORBIDDEN)
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        if meeting.landlord != user.landlord_profile:
            return Response({"error": "You can only manage meetings for your own properties."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = MeetingSerializer(meeting)
        return Response({"meeting": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = MeetingSerializer(meeting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Meeting updated successfully", "meeting": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        meeting.delete()
        return Response({"message": "Meeting cancelled successfully."}, status=status.HTTP_200_OK)


# ==================================================
# Lease Management
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lease_list_create(request):
    """
    List or create lease agreements.
    - GET: Shows only leases relevant to your role (admin sees all)
    - POST: Only admins/landlords can create leases
    - Automatically marks property as OCCUPIED when lease is set to ACTIVE
    - Landlords can only create leases for their own properties
    """
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can create leases."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']

            # Enforce property ownership check for landlords
            if user.role == 'landlord' and property_obj.landlord != getattr(user, "landlord_profile", None):
                return Response({"error": "You can only create leases for your own properties."}, status=status.HTTP_403_FORBIDDEN)

            lease = serializer.save()

            # Sync property status when lease becomes active
            if lease.status == "ACTIVE":
                property_obj.status = "OCCUPIED"
                property_obj.save(update_fields=['status'])

            return Response({"message": "Lease created successfully", "lease": serializer.data}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter leases based on user role
    if user.role == 'admin':
        leases = Lease.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        leases = Lease.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        leases = Lease.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        leases = Lease.objects.none()

    serializer = LeaseSerializer(leases, many=True)
    return Response({"leases": serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def lease_detail(request, lease_id):
    """
    View, update, or delete a single lease.
    - Automatically syncs property occupancy status when lease status changes
    - Tenants can only view, not edit or delete
    - Landlords can only manage leases for their own properties
    """
    user = request.user

    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        return Response({"error": "Lease not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access control checks
    if user.role == 'landlord' and hasattr(user, "landlord_profile") and lease.property.landlord != user.landlord_profile:
        return Response({"error": "You can only access leases for your own properties."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'tenant' and hasattr(user, "tenant") and lease.tenant != user.tenant:
        return Response({"error": "You can only view your own lease."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = LeaseSerializer(lease)
        return Response({"lease": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response({"error": "Tenants cannot edit leases."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated_lease = serializer.save()
            # Update property status to match new lease status
            updated_lease.property.status = "OCCUPIED" if updated_lease.status == "ACTIVE" else "AVAILABLE"
            updated_lease.property.save(update_fields=['status'])

            return Response({"message": "Lease updated successfully", "lease": serializer.data}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can delete leases."}, status=status.HTTP_403_FORBIDDEN)

        # Mark property as available when lease is removed
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
    """
    List or create system notices/announcements.
    - GET: Tenants see public notices; landlords see only their own
    - POST: Only admins and landlords can publish notices
    """
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can create notices."}, status=status.HTTP_403_FORBIDDEN)

        serializer = NoticeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=user)
            return Response({"message": "Notice created successfully", "notice": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter notices based on role
    if user.role == 'admin':
        notices = Notice.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        notices = Notice.objects.filter(created_by=user).order_by('-created_at')
    elif user.role == 'tenant':
        notices = Notice.objects.filter(Q(target='ALL') | Q(target='ALL TENANTS')).order_by('-created_at')
    else:
        notices = Notice.objects.none()

    serializer = NoticeSerializer(notices, many=True)
    return Response({"notices": serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def notice_detail(request, notice_id):
    """
    Manage a single notice.
    - Tenants can only view, cannot modify or delete
    - Landlords can only edit/delete notices they created themselves
    """
    user = request.user

    try:
        notice = Notice.objects.get(id=notice_id)
    except Notice.DoesNotExist:
        return Response({"error": "Notice not found."}, status=status.HTTP_404_NOT_FOUND)

    # Permission checks
    if user.role == 'tenant':
        if request.method != 'GET':
            return Response({"error": "Tenants cannot modify or delete notices."}, status=status.HTTP_403_FORBIDDEN)
    elif user.role == 'landlord' and notice.created_by != user:
        return Response({"error": "You can only manage notices you created."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = NoticeSerializer(notice)
        return Response({"notice": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = NoticeSerializer(notice, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Notice updated successfully", "notice": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        notice.delete()
        return Response({"message": "Notice deleted successfully."}, status=status.HTTP_200_OK)


# ==================================================
# Maintenance Requests
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def maintenance_list_create(request):
    """
    List or submit property maintenance requests.
    - GET: Filtered to show only requests relevant to your role
    - POST: Only tenants can submit new requests
    """
    user = request.user

    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit maintenance requests."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MaintenanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=user.tenant)
            return Response({"message": "Maintenance request submitted successfully", "maintenance": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter requests by role
    if user.role == 'admin':
        requests = Maintenance.objects.all().order_by('-created_at')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        requests = Maintenance.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant' and hasattr(user, "tenant"):
        requests = Maintenance.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        requests = Maintenance.objects.none()

    serializer = MaintenanceSerializer(requests, many=True)
    return Response({"maintenance_requests": serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def maintenance_detail(request, maintenance_id):
    """
    View, update, or delete a single maintenance request.
    - Tenants can only view their own requests, cannot delete
    - Landlords can update status and manage requests for their properties
    """
    user = request.user

    try:
        req = Maintenance.objects.get(id=maintenance_id)
    except Maintenance.DoesNotExist:
        return Response({"error": "Maintenance request not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access rules
    if user.role == 'tenant':
        if not hasattr(user, "tenant") or req.tenant != user.tenant:
            return Response({"error": "You can only access your own maintenance requests."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == 'DELETE':
            return Response({"error": "Tenants cannot delete maintenance requests."}, status=status.HTTP_403_FORBIDDEN)

    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        if req.property.landlord != user.landlord_profile:
            return Response({"error": "You can only manage requests for your own properties."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = MaintenanceSerializer(req)
        return Response({"maintenance": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = MaintenanceSerializer(req, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Maintenance request updated successfully", "maintenance": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can delete requests."}, status=status.HTTP_403_FORBIDDEN)
        req.delete()
        return Response({"message": "Maintenance request deleted successfully."})   


# ==================================================
# Payment System (Submission, History, Verification)
# ==================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def payment_list_create(request):
    """
    Submit rent payments or view payment history.
    - POST: Tenants only; auto-calculates which months payment covers (oldest first)
    - GET: Includes summary stats for collected/pending amounts
    - Enforces rule: clear old balances before paying new months
    """
    user = request.user

    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response({"error": "Only tenants can submit payments."}, status=status.HTTP_403_FORBIDDEN)

        serializer = PaymentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            lease = serializer.validated_data['lease']

            # Ensure tenant is paying for their own active lease
            if lease.tenant_id != user.tenant.id:
                return Response({"error": "You can only make payments for your own active leases."}, status=status.HTTP_403_FORBIDDEN)
            if lease.status != "ACTIVE":
                return Response({"error": "You can only pay for active leases."}, status=status.HTTP_400_BAD_REQUEST)
            if lease.end_date < datetime.today().date():
                return Response({"error": "Cannot submit payment — this lease has expired."}, status=status.HTTP_400_BAD_REQUEST)

            payment = serializer.save()

            # Auto-calculate which months this payment covers
            monthly_rent = Decimal(lease.monthly_rent)
            paid_amount = Decimal(payment.amount)
            covered_months = []
            remaining = paid_amount
            current = lease.start_date
            while remaining >= monthly_rent and current <= lease.end_date:
                covered_months.append(current.strftime("%B %Y"))
                remaining -= monthly_rent
                current = current.replace(year=current.year + 1, month=1) if current.month == 12 else current.replace(month=current.month + 1)

            payment.covered_months = covered_months
            payment.save(update_fields=['covered_months'])

            # Calculate current balance status
            total_completed = lease.payments.filter(status='COMPLETED').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            total_effective = total_completed + paid_amount
            new_balance = max(Decimal('0'), lease.monthly_rent - total_effective)

            # Build clear user response
            months_text = ", ".join(covered_months) if covered_months else ""
            extra_note = f" plus KSh {remaining:.2f} as advance credit" if remaining > 0 else ""
            success_msg = f"Payment submitted successfully! This covers: {months_text}{extra_note}. Awaiting verification." if covered_months else "Payment submitted successfully, awaiting verification."

            return Response(
                {
                    "message": success_msg,
                    "amount_paid": f"{paid_amount:.2f}",
                    "covers_months": covered_months,
                    "advance_credit_remaining": f"{remaining:.2f}" if remaining > 0 else "0.00",
                    "remaining_balance_due": f"{new_balance:.2f}",
                    "payment": PaymentSerializer(payment, context={'request': request}).data
                },
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Filter payment history based on role
    if user.role == 'admin':
        payments = Payment.objects.all().select_related('lease', 'lease__tenant', 'lease__property')
    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        payments = Payment.objects.filter(lease__property__landlord=user.landlord_profile).select_related('lease', 'lease__tenant', 'lease__property')
    elif user.role == 'tenant' and hasattr(user, "tenant") and user.is_active:
        payments = Payment.objects.filter(lease__tenant=user.tenant).select_related('lease', 'lease__tenant', 'lease__property')
    else:
        payments = Payment.objects.none()

    # Apply optional URL filters
    status_filter = request.query_params.get('status')
    lease_id = request.query_params.get('lease_id')
    tenant_id = request.query_params.get('tenant_id')
    if status_filter: payments = payments.filter(status=status_filter.upper())
    if lease_id: payments = payments.filter(lease_id=lease_id)
    if tenant_id and user.role in ['admin', 'landlord']: payments = payments.filter(lease__tenant_id=tenant_id)

    # Calculate summary figures for dashboard
    total_paid = sum(p.amount for p in payments.filter(status='COMPLETED')) or Decimal('0.00')
    total_pending = sum(p.amount for p in payments.filter(status='PENDING')) or Decimal('0.00')
    monthly_rent = payments.first().lease.monthly_rent if payments.exists() else Decimal('0.00')
    balance_due = max(Decimal('0.00'), monthly_rent - total_paid)
    clear_msg = f"⚠️ You currently owe KSh {balance_due:.2f}. Clear this balance before paying for new months." if balance_due > 0 else "✅ All payments are up to date!"

    serializer = PaymentSerializer(payments.order_by('-created_at'), many=True, context={'request': request})
    return Response({
        "summary": {
            "monthly_rent": f"{monthly_rent:.2f}",
            "total_paid": f"{total_paid:.2f}",
            "total_pending": f"{total_pending:.2f}",
            "balance_due": f"{balance_due:.2f}",
            "clear_message": clear_msg,
            "note": "Payments apply to the oldest unpaid month first."
        },
        "payments": serializer.data
    })


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    """
    Manage a single payment record.
    - Tenants can only view, cannot edit or delete
    - Receipt fields are auto-generated when payment is verified
    """
    try:
        payment = Payment.objects.select_related('lease', 'lease__property', 'lease__tenant').get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access rules
    if request.user.role == 'tenant' and hasattr(request.user, "tenant"):
        if payment.lease.tenant != request.user.tenant:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        if request.method in ['PUT', 'DELETE']:
            return Response({"error": "Only landlords or admins can modify payments."}, status=status.HTTP_403_FORBIDDEN)

    elif request.user.role == 'landlord' and hasattr(request.user, "landlord_profile"):
        if payment.lease.property.landlord != request.user.landlord_profile:
            return Response({"error": "You can only manage payments for your own properties."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"payment": PaymentSerializer(payment, context={'request': request}).data})

    if request.method == 'PUT':
        serializer = PaymentSerializer(payment, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Payment updated successfully.", "payment": serializer.data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if request.user.role != 'admin':
            return Response({"error": "Only system admins can delete payments."}, status=status.HTTP_403_FORBIDDEN)
        payment.delete()
        return Response({"message": "Payment deleted successfully."})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rent_for_month(request):
    """
    Check rent status for a specific month and active lease.
    Usage: /api/core/rent-for-month/?lease_id=1&month=2026-07
    Returns rent amount, payment status, and balance for that period.
    """
    # Get query parameters
    month = request.query_params.get('month')
    lease_id = request.query_params.get('lease_id')

    # Validate required params
    if not month:
        return Response(
            {"error": "Please provide month in format: ?month=2026-07"},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not lease_id:
        return Response(
            {"error": "Please provide lease ID: ?lease_id=1&month=2026-07"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate month format
    try:
        target_date = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        return Response(
            {"error": "Invalid date format. Use: ?month=2026-07"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Only allow active tenants
    if request.user.role != 'tenant' or not hasattr(request.user, "tenant"):
        return Response(
            {"error": "Only tenants can check rent status."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get the specific lease belonging to this tenant
    try:
        lease = Lease.objects.get(
            id=lease_id,
            tenant=request.user.tenant,
            status='ACTIVE'
        )
    except Lease.DoesNotExist:
        return Response(
            {"error": "Active lease not found or you do not have permission to access it."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check month falls within lease period
    if target_date < lease.start_date or target_date > lease.end_date:
        return Response(
            {"error": f"This lease runs from {lease.start_date} to {lease.end_date} — the requested month is outside this range."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Calculate totals
    total_paid = lease.payments.filter(status='COMPLETED').aggregate(
        Sum('amount')
    )['total'] or Decimal('0.00')
    paid_for_this = total_paid >= lease.monthly_rent

    # Return consistent response
    return Response({
        "month": target_date.strftime("%B %Y"),
        "lease_id": lease.id,
        "property": lease.property.title,
        "monthly_rent": float(lease.monthly_rent),
        "total_paid": float(total_paid),
        "status": "PAID" if paid_for_this else "PAYABLE",
        "amount_due": float(Decimal('0.00') if paid_for_this else lease.monthly_rent - total_paid),
        "note": "Payments are applied to the oldest outstanding balance first."
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def verify_payment(request, payment_id):
    """
    Verify pending payments (landlord/admin only).
    - Sets status to COMPLETED or FAILED
    - Auto-generates unique receipt number and timestamp for COMPLETED payments
    - Recalculates covered months and final balance
    """
    try:
        payment = Payment.objects.select_related('lease', 'lease__property', 'lease__tenant').get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

    user = request.user
    # Permission checks
    if user.role == 'tenant':
        return Response({"error": "Only landlords or admins can verify payments"}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'landlord' and hasattr(user, 'landlord_profile'):
        if payment.lease.property.landlord != user.landlord_profile:
            return Response({"error": "You can only verify payments for your own properties"}, status=status.HTTP_403_FORBIDDEN)

    # Validate input
    if payment.status != 'PENDING':
        return Response({"error": "Only pending payments can be verified"}, status=status.HTTP_400_BAD_REQUEST)
    new_status = request.data.get('status')
    if new_status not in ['COMPLETED', 'FAILED']:
        return Response({"error": "Invalid status. Must be 'COMPLETED' or 'FAILED'"}, status=status.HTTP_400_BAD_REQUEST)   
    
# ==================================================
# Admin Dashboard Statistics (Missing Function)
# ==================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard_stats(request):
    """
    Returns system-wide statistics for admin dashboard.
    Restricted to admin users only.
    """
    if request.user.role != 'admin':
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    from .models import Property, Lease, Payment, Tenant, Landlord, Maintenance, RentalRequest

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
        "properties": {"occupied": occupied, "vacant": vacant},
        "payments": {"total_collected": float(total_collected), "total_pending": float(total_pending)},
        "pending_actions": {"maintenance": pending_maintenance, "rental_requests": pending_requests}
    })


# ==================================================
# Admin All Users List (Missing Function)
# ==================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_users(request):
    """
    Returns full list of all system users for admin management.
    Restricted to admin users only.
    """
    if request.user.role != 'admin':
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    users = User.objects.all().order_by('-date_joined')
    data = []
    for user in users:
        item = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "date_joined": user.date_joined
        }
        data.append(item)

    return Response({"users": data})
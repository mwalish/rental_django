# from rest_framework import permissions
from decimal import Decimal

from rest_framework import permissions
from rest_framework.decorators import  api_view, permission_classes
from rest_framework.views import APIView 
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, date
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Q, Sum, Count

# ✅ All models imported correctly
from .models import Landlord, Lease, Payment, Tenant, Property, Notice, Maintenance, User

# ✅ All serializers imported correctly
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
    TenantCreateSerializer
)

User = get_user_model()

# ------------------------------
# Admin creates Landlord
# ------------------------------
class AdminCreateLandlordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Only allow admins
        if request.user.role != 'admin':
            return Response({"error": "Only admin can create landlords."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LandlordCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Landlord account created successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ------------------------------
# Landlord creates Tenant
# ------------------------------
class LandlordCreateTenantView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Only allow landlords
        if request.user.role != 'landlord':
            return Response({"error": "Only landlords can register tenants."}, status=status.HTTP_403_FORBIDDEN)

        serializer = TenantCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Tenant account created successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# --------------------------
# Register
# --------------------------
@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def Register(request):
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

        # ✅ Safely create related profile if it doesn't exist
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


# --------------------------
# Login
# --------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
def Login(request):
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=email, password=password)
    if not user:
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    profile_data = {}

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


# --------------------------
# Profile
# --------------------------
@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def ProfileView(request):
    user = request.user

    if user.role == "admin":
        return Response({"message": "Admin users do not have a separate profile."})

    try:
        if user.role == "landlord":
            if not hasattr(user, "landlord_profile"):
                return Response({"error": "Landlord profile not found."}, status=status.HTTP_404_NOT_FOUND)
            profile = user.landlord_profile
            if request.method == "GET":
                serializer = LandlordProfileSerializer(profile)
            else:
                serializer = LandlordProfileSerializer(profile, data=request.data, partial=True)

        elif user.role == "tenant":
            if not hasattr(user, "tenant"):
                return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)
            profile = user.tenant
            if request.method == "GET":
                serializer = TenantProfileSerializer(profile)
            else:
                serializer = TenantProfileSerializer(profile, data=request.data, partial=True)

        else:
            return Response({"error": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    except (Landlord.DoesNotExist, Tenant.DoesNotExist):
        return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(serializer.data)

    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Profile updated successfully", "profile": serializer.data})
    
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------
# LEASE VIEWS
# ------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lease_list_create(request):
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can create leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']

            if user.role == 'landlord' and property_obj.landlord != getattr(user, "landlord_profile", None):
                return Response(
                    {"error": "You can only create leases for your own properties."},
                    status=status.HTTP_403_FORBIDDEN
                )

            lease = serializer.save()

            if lease.status == "ACTIVE":
                property_obj.status = "OCCUPIED"
                property_obj.save(update_fields=['status'])

            return Response(
                {
                    "message": "Lease created successfully",
                    "lease": serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    user = request.user

    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        return Response(
            {"error": "Lease not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if user.role == 'landlord' and hasattr(user, "landlord_profile") and lease.property.landlord != user.landlord_profile:
        return Response(
            {"error": "You can only access leases for your own properties."},
            status=status.HTTP_403_FORBIDDEN
        )
    if user.role == 'tenant' and hasattr(user, "tenant") and lease.tenant != user.tenant:
        return Response(
            {"error": "You can only view your own lease."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == 'GET':
        serializer = LeaseSerializer(lease)
        return Response({"lease": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response(
                {"error": "Tenants cannot edit leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated_lease = serializer.save()
            if updated_lease.status == "ACTIVE":
                updated_lease.property.status = "OCCUPIED"
            else:
                updated_lease.property.status = "AVAILABLE"
            updated_lease.property.save(update_fields=['status'])

            return Response(
                {
                    "message": "Lease updated successfully",
                    "lease": serializer.data
                },
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can delete leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        lease.property.status = "AVAILABLE"
        lease.property.save(update_fields=['status'])
        lease.delete()

        return Response(
            {"message": "Lease deleted successfully."},
            status=status.HTTP_200_OK
        )


# ------------------------------
# NOTICE VIEWS
# ------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def notice_list_create(request):
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can create notices."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = NoticeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=user)
            return Response(
                {
                    "message": "Notice created successfully",
                    "notice": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    user = request.user

    try:
        notice = Notice.objects.get(id=notice_id)
    except Notice.DoesNotExist:
        return Response(
            {"error": "Notice not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if user.role == 'tenant':
        if request.method != 'GET':
            return Response(
                {"error": "Tenants cannot modify or delete notices."},
                status=status.HTTP_403_FORBIDDEN
            )
    elif user.role == 'landlord' and notice.created_by != user:
        return Response(
            {"error": "You can only manage notices you created."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == 'GET':
        serializer = NoticeSerializer(notice)
        return Response({"notice": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = NoticeSerializer(notice, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Notice updated successfully",
                    "notice": serializer.data
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        notice.delete()
        return Response(
            {"message": "Notice deleted successfully."},
            status=status.HTTP_200_OK
        )


# ------------------------------
# MAINTENANCE VIEWS
# ------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def maintenance_list_create(request):
    user = request.user

    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response(
                {"error": "Only tenants can submit maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = MaintenanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=user.tenant)
            return Response(
                {
                    "message": "Maintenance request submitted successfully",
                    "maintenance": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    user = request.user

    try:
        req = Maintenance.objects.get(id=maintenance_id)
    except Maintenance.DoesNotExist:
        return Response(
            {"error": "Maintenance request not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if user.role == 'tenant':
        if not hasattr(user, "tenant") or req.tenant != user.tenant:
            return Response(
                {"error": "You can only access your own maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )
        if request.method == 'DELETE':
            return Response(
                {"error": "Tenants cannot delete maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )

    elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
        if req.property.landlord != user.landlord_profile:
            return Response(
                {"error": "You can only manage requests for your own properties."},
                status=status.HTTP_403_FORBIDDEN
            )

    if request.method == 'GET':
        serializer = MaintenanceSerializer(req)
        return Response({"maintenance": serializer.data}, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        serializer = MaintenanceSerializer(req, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Maintenance request updated successfully",
                    "maintenance": serializer.data
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can delete requests."},
                status=status.HTTP_403_FORBIDDEN
            )
        req.delete()
        return Response(
            {"message": "Maintenance request deleted successfully."},
            status=status.HTTP_200_OK
        )   
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def payment_list_create(request):
    user = request.user

    if request.method == 'POST':
        if user.role != 'tenant' or not hasattr(user, "tenant"):
            return Response(
                {"error": "Only tenants can submit payments."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = PaymentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            lease = serializer.validated_data['lease']

            if lease.tenant_id != user.tenant.id:
                return Response(
                    {"error": "You can only make payments for your own active leases."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if lease.status != "ACTIVE":
                return Response(
                    {"error": "You can only pay for active leases."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Block payments for expired leases
            if lease.end_date < datetime.today().date():
                return Response(
                    {"error": "Cannot submit payment — this lease has expired."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payment = serializer.save()

            # ✅ Calculate which months this payment covers (oldest first)
            monthly_rent = Decimal(lease.monthly_rent)
            paid_amount = Decimal(payment.amount)
            covered_months = []
            remaining = paid_amount

            # Start from lease start date, go forward
            current = lease.start_date
            while remaining >= monthly_rent and current <= lease.end_date:
                month_label = current.strftime("%B %Y")  # e.g. "July 2026"
                covered_months.append(month_label)
                remaining -= monthly_rent
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)

            # ✅ Pass covered months to serializer so it shows correctly
            payment.covered_months = covered_months

            # ✅ Calculate remaining balance correctly (includes this new payment)
            total_completed = lease.payments.filter(status='COMPLETED').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            # New balance = rent minus ALL completed + this pending payment
            total_effective = total_completed + paid_amount
            new_balance = max(Decimal('0'), lease.monthly_rent - total_effective)

            # Build clear message
            if covered_months:
                months_text = ", ".join(covered_months)
                extra_note = f" plus KSh {remaining:.2f} as advance credit" if remaining > 0 else ""
                success_msg = f"Payment submitted successfully! This covers: {months_text}{extra_note}. Awaiting verification."
            else:
                success_msg = "Payment submitted successfully, awaiting verification."

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


    if request.method == 'GET':
        if user.role == 'admin':
            payments = Payment.objects.all().select_related('lease', 'lease__tenant', 'lease__property')
        elif user.role == 'landlord' and hasattr(user, "landlord_profile"):
            payments = Payment.objects.filter(lease__property__landlord=user.landlord_profile).select_related('lease', 'lease__tenant', 'lease__property')
        elif user.role == 'tenant' and hasattr(user, "tenant") and user.is_active:
            payments = Payment.objects.filter(lease__tenant=user.tenant).select_related('lease', 'lease__tenant', 'lease__property')
        else:
            payments = Payment.objects.none()

        status_filter = request.query_params.get('status')
        lease_id = request.query_params.get('lease_id')
        tenant_id = request.query_params.get('tenant_id')

        if status_filter:
            payments = payments.filter(status=status_filter.upper())
        if lease_id:
            payments = payments.filter(lease_id=lease_id)
        if tenant_id and user.role in ['admin', 'landlord']:
            payments = payments.filter(lease__tenant_id=tenant_id)

        # ✅ Initialize all variables FIRST to avoid UnboundLocalError
        total_paid = Decimal('0.00')
        total_pending = Decimal('0.00')
        monthly_rent = Decimal('0.00')

        if payments.exists():
            total_paid = sum(p.amount for p in payments.filter(status='COMPLETED')) or Decimal('0.00')
            total_pending = sum(p.amount for p in payments.filter(status='PENDING')) or Decimal('0.00')
            monthly_rent = payments.first().lease.monthly_rent

        balance_due = max(Decimal('0.00'), monthly_rent - total_paid)

        serializer = PaymentSerializer(payments, many=True, context={'request': request})

        return Response({
            "summary": {
                "monthly_rent": f"{monthly_rent:.2f}",
                "total_paid": f"{total_paid:.2f}",
                "total_pending": f"{total_pending:.2f}",
                "balance_due": f"{balance_due:.2f}",
                "clear_message": f"⚠️ You currently owe KSh {balance_due:.2f}. Clear this balance before paying for new months.",
                "note": "Payments apply to the oldest unpaid month first."
            },
            "payments": serializer.data
        })


# --- payment_detail function REMAINS 100% UNCHANGED ---
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.user.role == 'tenant' and hasattr(request.user, "tenant"):
        if payment.lease.tenant != request.user.tenant:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        if request.method in ['PUT', 'DELETE']:
            return Response({"error": "Only landlords/admins can update payments."}, status=status.HTTP_403_FORBIDDEN)

    elif request.user.role == 'landlord' and hasattr(request.user, "landlord_profile"):
        if payment.lease.property.landlord != request.user.landlord_profile:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = PaymentSerializer(payment, context={'request': request})
        return Response({"payment": serializer.data})

    if request.method == 'PUT':
        serializer = PaymentSerializer(payment, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Payment updated successfully.",
                "payment": serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if request.user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins can delete payments."}, status=status.HTTP_403_FORBIDDEN)
        payment.delete()
        return Response({"message": "Payment deleted."})


# ------------------------------
# Check Rent For Specific Month
# ------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rent_for_month(request):
    month = request.query_params.get('month')
    if not month:
        return Response({"error": "Please provide month like: ?month=2026-08"}, status=400)

    try:
        target_date = datetime.strptime(month, "%Y-%m").date()
    except:
        return Response({"error": "Use format: ?month=2026-08"}, status=400)

    if request.user.role == 'tenant' and hasattr(request.user, "tenant") and request.user.is_active:
        lease = Lease.objects.filter(tenant=request.user.tenant, status='ACTIVE').first()
        if not lease:
            return Response({"error": "No active lease found."}, status=404)

        if target_date < lease.start_date or target_date > lease.end_date:
            return Response({"error": "This month is not covered by your lease."}, status=400)

        month_name = target_date.strftime("%B %Y")
        total_paid = lease.payments.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        paid_for_this = total_paid >= lease.monthly_rent

        return Response({
            "month": month_name,
            "monthly_rent": f"{lease.monthly_rent:.2f}",
            "status": "PAID" if paid_for_this else "PAYABLE",
            "amount_to_pay": "0.00" if paid_for_this else f"{lease.monthly_rent:.2f}",
            "note": "Payments clear oldest balance first."
        })

    return Response({"error": "Only active tenants can check this."}, status=status.HTTP_403_FORBIDDEN)
# ------------------------------
# ✅ SUPER ADMIN DASHBOARD API
# ------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard_stats(request):
    """Get all system statistics for Super Admin only"""
    if request.user.role != 'admin':
        return Response({"error": "Only system administrators can access this data."}, status=status.HTTP_403_FORBIDDEN)

    total_users = User.objects.count()
    total_landlords = Landlord.objects.count()
    total_tenants = Tenant.objects.count()
    total_properties = Property.objects.count()

    available_properties = Property.objects.filter(status='AVAILABLE').count()
    occupied_properties = Property.objects.filter(status='OCCUPIED').count()
    under_repair = Property.objects.filter(status='MAINTENANCE').count()

    pending_leases = Lease.objects.filter(status='PENDING').count()
    active_leases = Lease.objects.filter(status='ACTIVE').count()

    pending_maintenance = Maintenance.objects.filter(status='PENDING').count()
    completed_maintenance = Maintenance.objects.filter(status='COMPLETED').count()

    total_revenue = Payment.objects.filter(status='COMPLETED').aggregate(total=Sum('amount'))['total'] or 0
    pending_payments = Payment.objects.filter(status='PENDING').aggregate(total=Sum('amount'))['total'] or 0

    return Response({
        "users": {
            "total": total_users,
            "landlords": total_landlords,
            "tenants": total_tenants
        },
        "properties": {
            "total": total_properties,
            "available": available_properties,
            "occupied": occupied_properties,
            "under_repair": under_repair
        },
        "leases": {
            "active": active_leases,
            "pending": pending_leases
        },
        "maintenance": {
            "pending": pending_maintenance,
            "completed": completed_maintenance
        },
        "payments": {
            "total_revenue": round(total_revenue, 2),
            "pending_amount": round(pending_payments, 2)
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_users(request):
    """List all users in the system"""
    if request.user.role != 'admin':
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    users = User.objects.all().order_by('-date_joined')
    serializer = UserSerializer(users, many=True)
    return Response({"users": serializer.data})
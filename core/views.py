from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Landlord, Lease, Payment, Tenant, Property,Notice , Maintenance #notice 

from .serializers import (
    LeaseSerializer,
    MaintenanceSerializer,
    NoticeSerializer,
    PaymentSerializer,
    UserRegistrationSerializer,
    UserSerializer,
    LandlordProfileSerializer,
    TenantProfileSerializer
)

User = get_user_model()


# --------------------------
# Register
# --------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
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

        if requested_role == "landlord":
            profile = user.landlord_profile
            profile.full_name = request.data.get("full_name", profile.full_name)
            profile.id_number = request.data.get("id_number")
            profile.mpesa_number = request.data.get("mpesa_number")
            profile.address = request.data.get("address")
            profile.business_name = request.data.get("business_name", "")
            profile.license_number = request.data.get("license_number", "")
            profile.save()

        elif requested_role == "tenant":
            profile = user.tenant
            profile.full_name = request.data.get("full_name", profile.full_name)
            profile.id_number = request.data.get("id_number")
            profile.alternative_phone = request.data.get("alternative_phone", "")
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

    if user.role == "landlord":
        profile_data = LandlordProfileSerializer(user.landlord_profile).data
    elif user.role == "tenant":
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
            profile = user.landlord_profile
            # ✅ GET: ONLY pass the instance, NO data=
            if request.method == "GET":
                serializer = LandlordProfileSerializer(profile)
            else:
                # ✅ PUT/PATCH: pass data and partial update
                serializer = LandlordProfileSerializer(profile, data=request.data, partial=True)

        elif user.role == "tenant":
            profile = user.tenant
            if request.method == "GET":
                serializer = TenantProfileSerializer(profile)
            else:
                serializer = TenantProfileSerializer(profile, data=request.data, partial=True)

        else:
            return Response({"error": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    except (Landlord.DoesNotExist, Tenant.DoesNotExist):
        return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Return directly for GET, no validation needed
    if request.method == "GET":
        return Response(serializer.data)

    # ✅ Validate only for update requests
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

    # Create new lease
    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can create leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']

            # Landlord can only use their own property
            if user.role == 'landlord' and property_obj.landlord != user.landlord_profile:
                return Response(
                    {"error": "You can only create leases for your own properties."},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Save lease — your model will auto-fill monthly_rent
            lease = serializer.save()

            # Update property status
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

    # List leases filtered by user role
    if user.role == 'admin':
        leases = Lease.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        leases = Lease.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant':
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

    # Access control
    if user.role == 'landlord' and lease.property.landlord != user.landlord_profile:
        return Response(
            {"error": "You can only access leases for your own properties."},
            status=status.HTTP_403_FORBIDDEN
        )
    if user.role == 'tenant' and lease.tenant != user.tenant:
        return Response(
            {"error": "You can only view your own lease."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get single lease
    if request.method == 'GET':
        serializer = LeaseSerializer(lease)
        return Response({"lease": serializer.data}, status=status.HTTP_200_OK)

    # Update lease
    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response(
                {"error": "Tenants cannot edit leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated_lease = serializer.save()
            # Sync property status
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

    # Delete lease
    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can delete leases."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Set property back to available
        lease.property.status = "AVAILABLE"
        lease.property.save(update_fields=['status'])
        lease.delete()

        return Response(
            {"message": "Lease deleted successfully."},
            status=status.HTTP_200_OK
        )
    
    #start td
    # ------------------------------
# NOTICE VIEWS
# ------------------------------
from .models import Notice  # Add this line if not already imported


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def notice_list_create(request):
    user = request.user

    # --- Create new notice ---
    if request.method == 'POST':
        # Only Admin and Landlord can create notices
        if user.role not in ['admin', 'landlord']:
            return Response(
                {"error": "Only admins and landlords can create notices."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = NoticeSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-set creator to current logged-in user
            serializer.save(created_by=user)
            return Response(
                {
                    "message": "Notice created successfully",
                    "notice": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --- List notices ---
    if user.role == 'admin':
        # Admin sees all notices
        notices = Notice.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        # Landlord sees only notices they created
        notices = Notice.objects.filter(created_by=user).order_by('-created_at')
    elif user.role == 'tenant':
        # Tenant sees only notices targeted to ALL
        notices = Notice.objects.filter(target='ALL').order_by('-created_at')
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

    # --- Access control ---
    if user.role == 'tenant':
        # Tenants can only view, not edit/delete
        if request.method != 'GET':
            return Response(
                {"error": "Tenants cannot modify or delete notices."},
                status=status.HTTP_403_FORBIDDEN
            )
    elif user.role == 'landlord':
        # Landlords can only edit/delete their own notices
        if notice.created_by != user:
            return Response(
                {"error": "You can only manage notices you created."},
                status=status.HTTP_403_FORBIDDEN
            )

    # --- Get single notice ---
    if request.method == 'GET':
        serializer = NoticeSerializer(notice)
        return Response({"notice": serializer.data}, status=status.HTTP_200_OK)

    # --- Update notice ---
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

    # --- Delete notice ---
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

    # --- Create new maintenance request ---
    if request.method == 'POST':
        # Only tenants can submit maintenance requests
        if user.role != 'tenant':
            return Response(
                {"error": "Only tenants can submit maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = MaintenanceSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-link to current tenant
            serializer.save(tenant=user.tenant)
            return Response(
                {
                    "message": "Maintenance request submitted successfully",
                    "maintenance": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --- List maintenance requests ---
    if user.role == 'admin':
        # Admin sees all requests
        requests = Maintenance.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        # Landlord sees only requests for their own properties
        requests = Maintenance.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant':
        # Tenant sees only their own requests
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

    # --- Access control ---
    if user.role == 'tenant':
        # Tenant can only view/update their own requests, can't delete
        if req.tenant != user.tenant:
            return Response(
                {"error": "You can only access your own maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )
        if request.method == 'DELETE':
            return Response(
                {"error": "Tenants cannot delete maintenance requests."},
                status=status.HTTP_403_FORBIDDEN
            )

    elif user.role == 'landlord':
        # Landlord can only manage requests for their own properties
        if req.property.landlord != user.landlord_profile:
            return Response(
                {"error": "You can only manage requests for your own properties."},
                status=status.HTTP_403_FORBIDDEN
            )

    # --- Get single request ---
    if request.method == 'GET':
        serializer = MaintenanceSerializer(req)
        return Response({"maintenance": serializer.data}, status=status.HTTP_200_OK)

    # --- Update request (change status, edit details) ---
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

    # --- Delete request ---
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
    """
    GET  - List payments with filters, totals and balance summary
    POST - Create new payment (only for tenants)
    """
    user = request.user

    # --------------------------
    # CREATE NEW PAYMENT
    # --------------------------
    if request.method == 'POST':
        # Only tenants can submit payments
        if user.role != 'tenant':
            return Response(
                {"error": "Only tenants can submit payments."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Make sure tenant profile exists
        if not hasattr(user, 'tenant') or user.tenant is None:
            return Response(
                {"error": "Tenant profile not found."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate input data
        serializer = PaymentSerializer(data=request.data)
        if serializer.is_valid():
            lease = serializer.validated_data['lease']

            # Security check: only allow payments for the tenant's own active lease
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

            # Save payment record
            payment = serializer.save()
            return Response(
                {
                    "message": "Payment submitted successfully, awaiting verification.",
                    "payment": PaymentSerializer(payment, context={'request': request}).data
                },
                status=status.HTTP_201_CREATED
            )

        # Return errors if data is invalid
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    # --------------------------
    # LIST PAYMENTS + FILTERS + SUMMARY
    # --------------------------
    if request.method == 'GET':
        # Base query: show only what the user is allowed to see
        if user.role == 'admin':
            payments = Payment.objects.all().select_related('lease', 'lease__tenant', 'lease__property')
        elif user.role == 'landlord':
            payments = Payment.objects.filter(lease__property__landlord=user.landlord_profile).select_related('lease', 'lease__tenant', 'lease__property')
        elif user.role == 'tenant':
            payments = Payment.objects.filter(lease__tenant=user.tenant).select_related('lease', 'lease__tenant', 'lease__property')
        else:
            payments = Payment.objects.none()

        # --------------------------
        # APPLY FILTERS
        # --------------------------
        status_filter = request.query_params.get('status')   # e.g. ?status=pending
        lease_id = request.query_params.get('lease_id')     # e.g. ?lease_id=4
        tenant_id = request.query_params.get('tenant_id')   # e.g. ?tenant_id=3

        if status_filter:
            payments = payments.filter(status=status_filter.lower())
        if lease_id:
            payments = payments.filter(lease_id=lease_id)
        # Only admins/landlords can filter by tenant
        if tenant_id and user.role in ['admin', 'landlord']:
            payments = payments.filter(lease__tenant_id=tenant_id)

        # --------------------------
        # CALCULATE TOTALS & BALANCE
        # --------------------------
        total_paid = sum(p.amount for p in payments.filter(status='completed'))
        total_pending = sum(p.amount for p in payments.filter(status='pending'))

        # Get monthly rent amount from the lease
        monthly_rent = payments.first().lease.monthly_rent if payments.exists() else 0

        # Calculate balance: how much more is still due
        balance_due = max(0, monthly_rent - total_paid)

        # --------------------------
        # SEND RESPONSE
        # --------------------------
        serializer = PaymentSerializer(payments, many=True, context={'request': request})

        return Response({
            "summary": {
                "monthly_rent": f"{monthly_rent:.2f}",
                "total_paid": f"{total_paid:.2f}",
                "total_pending": f"{total_pending:.2f}",
                "balance_due": f"{balance_due:.2f}"
            },
            "payments": serializer.data
        })


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    """
    GET    - View single payment details
    PUT    - Update payment (only landlord/admin can approve/change status)
    DELETE - Remove payment record
    """
    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

    # --------------------------
    # ACCESS CONTROL
    # --------------------------
    if request.user.role == 'tenant':
        # Tenants can only view their own payments
        if payment.lease.tenant != request.user.tenant:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        # Tenants cannot update or delete
        if request.method in ['PUT', 'DELETE']:
            return Response({"error": "Only landlords/admins can update payments."}, status=status.HTTP_403_FORBIDDEN)

    elif request.user.role == 'landlord':
        # Landlords only manage payments for their own properties
        if payment.lease.property.landlord != request.user.landlord_profile:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    # --------------------------
    # GET SINGLE PAYMENT
    # --------------------------
    if request.method == 'GET':
        serializer = PaymentSerializer(payment, context={'request': request})
        return Response({"payment": serializer.data})

    # --------------------------
    # UPDATE / APPROVE PAYMENT
    # --------------------------
    if request.method == 'PUT':
        serializer = PaymentSerializer(payment, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Payment updated successfully.",
                "payment": serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --------------------------
    # DELETE PAYMENT
    # --------------------------
    if request.method == 'DELETE':
        if request.user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins can delete payments."}, status=status.HTTP_403_FORBIDDEN)
        payment.delete()
        return Response({"message": "Payment deleted."})
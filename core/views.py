from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Landlord, Lease, Tenant, Property

from .serializers import (
    LeaseSerializer,
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
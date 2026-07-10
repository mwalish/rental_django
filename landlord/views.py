from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q
from datetime import datetime


# from .models import Lease, Property
# from .serializers import LeaseSerializer

# Import shared models and serializers from core
from core.models import Landlord, Property, RentalRequest, Meeting, Lease, Payment
from core.serializers import (
    LandlordProfileSerializer,
    PropertySerializer,
    RentalRequestSerializer,
    MeetingSerializer,
    LeaseSerializer,
    PaymentSerializer
)


# -----------------------------------------------------
# Helper: Verify logged-in user is a valid Landlord
# -----------------------------------------------------
def get_valid_landlord(user):
    if not user.is_authenticated or user.role != "landlord":
        return None
    try:
        return user.landlord_profile
    except Landlord.DoesNotExist:
        return None
@api_view(["GET"])

@permission_classes([IsAuthenticated])
def dashboard(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    # Properties
    properties = Property.objects.filter(landlord=landlord)
    total_properties = properties.count()
    available_properties = properties.filter(status="AVAILABLE").count()
    occupied_properties = properties.filter(status="OCCUPIED").count()

    # Leases
    leases = Lease.objects.filter(property__landlord=landlord)
    active_leases = leases.filter(status="ACTIVE").count()
    expired_leases = leases.filter(status="EXPIRED").count()

    # Rental Requests
    pending_requests = RentalRequest.objects.filter(
        property__landlord=landlord, status="PENDING"
    ).count()
    approved_requests = RentalRequest.objects.filter(
        property__landlord=landlord, status="APPROVED"
    ).count()

    # ✅ Payments — matches your model exactly
    payments = Payment.objects.filter(
        lease__property__landlord=landlord,
        status="completed"  # only count successful payments
    )
    total_income = payments.aggregate(total=Sum("amount"))["total"] or 0

    # This month's income
    today = datetime.today()
    monthly_income = payments.filter(
        payment_date__year=today.year,
        payment_date__month=today.month
    ).aggregate(month_total=Sum("amount"))["month_total"] or 0

    data = {
        "summary": {
            "total_properties": total_properties,
            "available_properties": available_properties,
            "occupied_properties": occupied_properties,
            "active_leases": active_leases,
            "expired_leases": expired_leases,
            "pending_rental_requests": pending_requests,
            "approved_rental_requests": approved_requests,
            "total_income_received": float(total_income),
            "current_month_income": float(monthly_income)
        },
        # not a must
        "quick_links": {
            "properties": "/api/landlord/properties/",
            "requests": "/api/landlord/rental-requests/",
            "leases": "/api/landlord/leases/",
            "payments": "/api/landlord/payments/"
        }
    }

    return Response({
        "message": "Dashboard loaded successfully",
        "data": data
    })


# --------------------------
# Landlord Profile
# --------------------------
@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def profile(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response(
            {"error": "Access denied. Only landlords can use this endpoint."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "GET":
        serializer = LandlordProfileSerializer(landlord)
        return Response(serializer.data)

    serializer = LandlordProfileSerializer(landlord, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(
            {"message": "Profile updated successfully", "data": serializer.data}
        )
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# --------------------------
# Property Management
# --------------------------
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def property_list(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        properties = Property.objects.filter(landlord=landlord)
        serializer = PropertySerializer(properties, many=True)
        return Response(serializer.data)

    serializer = PropertySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(landlord=landlord)
        return Response(
            {"message": "Property added successfully", "data": serializer.data},
            status=status.HTTP_201_CREATED
        )
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def property_detail(request, pk):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        property_obj = Property.objects.get(pk=pk, landlord=landlord)
    except Property.DoesNotExist:
        return Response(
            {"error": "Property not found or you do not have permission"},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = PropertySerializer(property_obj)
        return Response(serializer.data)

    if request.method in ["PUT", "PATCH"]:
        serializer = PropertySerializer(property_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Property updated successfully", "data": serializer.data}
            )
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        property_obj.delete()
        return Response({"message": "Property deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


# --------------------------
# View Rental Requests
# --------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def rental_requests(request, pk=None):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    if pk is None:
        requests = RentalRequest.objects.filter(property__landlord=landlord)
        serializer = RentalRequestSerializer(requests, many=True)
        return Response(serializer.data)

    try:
        req = RentalRequest.objects.get(pk=pk, property__landlord=landlord)
    except RentalRequest.DoesNotExist:
        return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = RentalRequestSerializer(req, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Request updated", "data": serializer.data})
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# --------------------------
# View Meetings
# --------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meetings(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    meetings = Meeting.objects.filter(property__landlord=landlord)
    serializer = MeetingSerializer(meetings, many=True)
    return Response(serializer.data)


# --------------------------
# View Leases
# --------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def leases(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    leases = Lease.objects.filter(property__landlord=landlord)
    serializer = LeaseSerializer(leases, many=True)
    return Response(serializer.data)


# --------------------------
# View Payments
# --------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payments(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    payments = Payment.objects.filter(lease__property__landlord=landlord)
    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data)


# ------------------------------
# LEASE MODULE VIEWS
# ------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lease_list_create(request):
    user = request.user

    # Create new lease
    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can create leases."}, status=403)

        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']
            # Landlord can only use their own property
            if user.role == 'landlord' and property_obj.landlord != user.landlord_profile:
                return Response({"error": "You can only create leases for your own properties."}, status=403)

            # Save — your model will auto-fill monthly_rent
            lease = serializer.save()

            # Update property status
            if lease.status == "ACTIVE":
                property_obj.status = "OCCUPIED"
                property_obj.save(update_fields=['status'])

            return Response({
                "message": "Lease created successfully",
                "lease": serializer.data
            }, status=201)
        return Response({"error": serializer.errors}, status=400)

    # List leases filtered by role
    if user.role == 'admin':
        leases = Lease.objects.all().order_by('-created_at')
    elif user.role == 'landlord':
        leases = Lease.objects.filter(property__landlord=user.landlord_profile).order_by('-created_at')
    elif user.role == 'tenant':
        leases = Lease.objects.filter(tenant=user.tenant).order_by('-created_at')
    else:
        leases = Lease.objects.none()

    serializer = LeaseSerializer(leases, many=True)
    return Response({"leases": serializer.data})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def lease_detail(request, lease_id):
    user = request.user

    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        return Response({"error": "Lease not found."}, status=404)

    # Access control
    if user.role == 'landlord' and lease.property.landlord != user.landlord_profile:
        return Response({"error": "You can only access leases for your own properties."}, status=403)
    if user.role == 'tenant' and lease.tenant != user.tenant:
        return Response({"error": "You can only view your own lease."}, status=403)

    # Get single lease
    if request.method == 'GET':
        serializer = LeaseSerializer(lease)
        return Response({"lease": serializer.data})

    # Update lease
    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response({"error": "Tenants cannot edit leases."}, status=403)

        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated_lease = serializer.save()
            # Sync property status
            if updated_lease.status == "ACTIVE":
                updated_lease.property.status = "OCCUPIED"
            else:
                updated_lease.property.status = "AVAILABLE"
            updated_lease.property.save(update_fields=['status'])
            return Response({
                "message": "Lease updated successfully",
                "lease": serializer.data
            })
        return Response({"error": serializer.errors}, status=400)

    # Delete lease
    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can delete leases."}, status=403)
        lease.property.status = "AVAILABLE"
        lease.property.save(update_fields=['status'])
        lease.delete()
        return Response({"message": "Lease deleted successfully."})
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q
from django.db import transaction
from datetime import datetime
from django.conf import settings

User = settings.AUTH_USER_MODEL

from core.models import Landlord, Property, RentalRequest, Meeting, Lease, Payment, Tenant
from core.serializers import (
    LandlordProfileSerializer,
    PropertySerializer,
    RentalRequestSerializer,
    MeetingSerializer,
    LeaseSerializer,
    PaymentSerializer,
    TenantProfileSerializer
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


# -----------------------------------------------------
# Dashboard
# -----------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    properties = Property.objects.filter(landlord=landlord)
    total_properties = properties.count()
    available_properties = properties.filter(status="AVAILABLE").count()
    occupied_properties = properties.filter(status="OCCUPIED").count()

    leases = Lease.objects.filter(property__landlord=landlord)
    active_leases = leases.filter(status="ACTIVE").count()
    expired_leases = leases.filter(status="EXPIRED").count()

    pending_requests = RentalRequest.objects.filter(
        property__landlord=landlord, status="PENDING"
    ).count()
    approved_requests = RentalRequest.objects.filter(
        property__landlord=landlord, status="APPROVED"
    ).count()

    payments = Payment.objects.filter(
        lease__property__landlord=landlord,
        status="completed"
    )
    total_income = payments.aggregate(total=Sum("amount"))["total"] or 0

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


# -----------------------------------------------------
# Landlord Profile
# -----------------------------------------------------
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


# -----------------------------------------------------
# Property Management
# -----------------------------------------------------
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


# -----------------------------------------------------
# Property Applicants — who applied for each house
# -----------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def property_applicants(request, property_id):
    """Return all rental requests (applicants) for one of the landlord's properties."""
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        prop = Property.objects.get(id=property_id, landlord=landlord)
    except Property.DoesNotExist:
        return Response({"error": "Property not found"}, status=status.HTTP_404_NOT_FOUND)

    reqs = RentalRequest.objects.filter(property=prop).select_related('tenant', 'landlord').order_by('-created_at')
    serializer = RentalRequestSerializer(reqs, many=True)
    return Response({"applicants": serializer.data})


# -----------------------------------------------------
# Rental Requests
# -----------------------------------------------------
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
        new_status = serializer.validated_data.get('status', req.status)
        serializer.save()

        # Auto-grant tenant privileges when a request is approved —
        # reuses the existing account; never creates a duplicate.
        converted_info = None
        if new_status == 'APPROVED':
            from core.views import convert_lead_to_tenant_account
            if req.tenant or req.lead_name or req.lead_phone or req.lead_email:
                converted_info = convert_lead_to_tenant_account(request.user, req, landlord=landlord)

        data = RentalRequestSerializer(req).data
        if converted_info:
            data['converted_tenant'] = converted_info
        return Response({"message": "Request updated", "data": data})
    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# -----------------------------------------------------
# Meetings — FULL CRUD + AUTO-SET LANDLORD ✅
# -----------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def meetings(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        # ✅ Fetch all related data in one query — avoids missing data errors
        meetings = Meeting.objects.filter(property__landlord=landlord).select_related('landlord', 'tenant', 'property')
        serializer = MeetingSerializer(meetings, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        serializer = MeetingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(landlord=landlord)
            return Response(
                {"message": "Meeting scheduled", "data": serializer.data},
                status=status.HTTP_201_CREATED
            )
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def meeting_detail(request, pk):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        meeting = Meeting.objects.get(pk=pk, property__landlord=landlord)
    except Meeting.DoesNotExist:
        return Response({"error": "Meeting not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(MeetingSerializer(meeting).data)

    if request.method == "PUT":
        s = MeetingSerializer(meeting, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response({"message": "Updated", "data": s.data})
        return Response({"error": s.errors}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        meeting.delete()
        return Response({"message": "Deleted"})


# -----------------------------------------------------
# Payments — FULL CRUD ✅
# -----------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def payments(request):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        payments = Payment.objects.filter(lease__property__landlord=landlord)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        serializer = PaymentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Payment recorded", "data": serializer.data},
                status=status.HTTP_201_CREATED
            )
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def payment_detail(request, pk):
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        pay = Payment.objects.get(pk=pk, lease__property__landlord=landlord)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(PaymentSerializer(pay).data)

    if request.method == "PUT":
        s = PaymentSerializer(pay, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response({"message": "Updated", "data": s.data})
        return Response({"error": s.errors}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        pay.delete()
        return Response({"message": "Deleted"})


# -----------------------------------------------------
# Leases — FULL CRUD
# -----------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lease_list_create(request):
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can create leases."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LeaseSerializer(data=request.data)
        if serializer.is_valid():
            property_obj = serializer.validated_data['property']
            if user.role == 'landlord' and property_obj.landlord != user.landlord_profile:
                return Response({"error": "You can only create leases for your own properties."}, status=status.HTTP_403_FORBIDDEN)

            lease = serializer.save()

            if lease.status == "ACTIVE":
                property_obj.status = "OCCUPIED"
            else:
                property_obj.status = "AVAILABLE"
            property_obj.save(update_fields=['status'])

            return Response({
                "message": "Lease created successfully",
                "lease": serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

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
        return Response({"error": "Lease not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'landlord' and lease.property.landlord != user.landlord_profile:
        return Response({"error": "You can only access leases for your own properties."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'tenant' and lease.tenant != user.tenant:
        return Response({"error": "You can only view your own lease."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = LeaseSerializer(lease)
        return Response({"lease": serializer.data})

    if request.method == 'PUT':
        if user.role == 'tenant':
            return Response({"error": "Tenants cannot edit leases."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        if serializer.is_valid():
            updated_lease = serializer.save()
            if updated_lease.status == "ACTIVE":
                updated_lease.property.status = "OCCUPIED"
            else:
                updated_lease.property.status = "AVAILABLE"
            updated_lease.property.save(update_fields=['status'])
            return Response({
                "message": "Lease updated successfully",
                "lease": serializer.data
            })
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only admins and landlords can delete leases."}, status=status.HTTP_403_FORBIDDEN)
        lease.property.status = "AVAILABLE"
        lease.property.save(update_fields=['status'])
        lease.delete()
        return Response({"message": "Lease deleted successfully."})


# -----------------------------------------------------
# Tenants — List tenants linked to the landlord's properties
# -----------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenants(request):
    """List ALL tenants the landlord can see:
      - tenants explicitly registered by this landlord,
      - tenants who hold a lease on the landlord's properties,
      - tenants who have an APPROVED rental request on the landlord's properties.

    The landlord can view full details on every one of these — including
    tenants they personally registered and approved applicants.
    """
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    # Tenants explicitly registered by this landlord + tenants on this landlord's leases
    registered_ids = Tenant.objects.filter(registered_by=landlord).values_list('id', flat=True)
    leased_ids = Lease.objects.filter(
        property__landlord=landlord
    ).values_list('tenant', flat=True).distinct()

    # Tenants with APPROVED rental requests on the landlord's properties
    approved_req_ids = RentalRequest.objects.filter(
        property__landlord=landlord, status="APPROVED", tenant__isnull=False
    ).values_list('tenant', flat=True).distinct()

    combined_ids = set(registered_ids) | set(leased_ids) | set(approved_req_ids)
    tenants_qs = Tenant.objects.filter(id__in=combined_ids).order_by('full_name')
    serializer = TenantProfileSerializer(tenants_qs, many=True)
    return Response(serializer.data)


# -----------------------------------------------------
# Registered Tenants — Only tenants this landlord created
# -----------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registered_tenants(request):
    """Return ONLY the tenants this landlord has registered (via Register Tenant).

    Used by the lease-creation form so the landlord can select from the
    tenants they personally registered — not every tenant in the system.
    """
    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    qs = Tenant.objects.filter(registered_by=landlord).order_by('full_name')
    serializer = TenantProfileSerializer(qs, many=True)
    return Response({"tenants": serializer.data})


# -----------------------------------------------------
# Convert a house-hunting lead into a registered tenant
# -----------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def convert_lead_to_tenant(request, request_id):
    """Promote a rental request lead into a full tenant account.

    Key principle: REUSE an existing account whenever possible — never create
    a duplicate. If the lead already has an account (by email, normalized phone,
    or full-name match), that exact account is granted the tenant role/privilege
    and linked to the request. A brand-new account is created ONLY as a last
    resort when nothing matches.
    """
    from core.views import convert_lead_to_tenant_account

    landlord = get_valid_landlord(request.user)
    if not landlord:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        req = RentalRequest.objects.get(pk=request_id, property__landlord=landlord)
    except RentalRequest.DoesNotExist:
        return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

    result = convert_lead_to_tenant_account(request.user, req, landlord=landlord)
    return Response(result)
    
    
    
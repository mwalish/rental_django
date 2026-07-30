from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q
from decimal import Decimal

from core.models import Tenant, Lease, Maintenance, Payment, RentalRequest, Property, Notice
from core.serializers import (
    TenantProfileSerializer, LeaseSerializer, MaintenanceSerializer,
    PaymentSerializer, RentalRequestSerializer, NoticeSerializer
)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def my_profile(request):
    """View or update the logged-in tenant's profile."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied. Tenants only."}, status=status.HTTP_403_FORBIDDEN)

    try:
        tenant = user.tenant
    except Tenant.DoesNotExist:
        return Response({"error": "Tenant profile not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(TenantProfileSerializer(tenant).data)

    serializer = TenantProfileSerializer(tenant, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Profile updated successfully", "profile": serializer.data})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_leases(request):
    """List all leases for the logged-in tenant."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    leases = Lease.objects.filter(tenant=user.tenant).order_by('-created_at')
    return Response({"leases": LeaseSerializer(leases, many=True).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_maintenance_requests(request):
    """List all maintenance requests submitted by the logged-in tenant."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    requests = Maintenance.objects.filter(tenant=user.tenant).order_by('-created_at')
    return Response({"maintenance_requests": MaintenanceSerializer(requests, many=True).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_maintenance_request(request):
    """Submit a new maintenance request."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Only tenants can submit maintenance requests."}, status=status.HTTP_403_FORBIDDEN)

    serializer = MaintenanceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(tenant=user.tenant)
        return Response({"message": "Maintenance request submitted.", "maintenance": serializer.data}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_payments(request):
    """View payment history for the logged-in tenant."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    payments = Payment.objects.filter(lease__tenant=user.tenant).order_by('-created_at')
    total_paid = payments.filter(status='COMPLETED').aggregate(t=Sum('amount'))['t'] or Decimal('0')

    return Response({
        "total_paid": float(total_paid),
        "payments": PaymentSerializer(payments, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_rental_requests(request):
    """View rental application history for the logged-in tenant."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    requests = RentalRequest.objects.filter(tenant=user.tenant).order_by('-created_at')
    return Response({"rental_requests": RentalRequestSerializer(requests, many=True).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_notices(request):
    """View notices relevant to tenants."""
    user = request.user
    if user.role != 'tenant':
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    notices = Notice.objects.filter(Q(target='ALL') | Q(target='ALL TENANTS')).order_by('-created_at')
    return Response({"notices": NoticeSerializer(notices, many=True).data})


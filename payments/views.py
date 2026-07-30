from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.models import Payment, Lease
from core.serializers import PaymentSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_summary(request):
    """Get an overview/summary of payments for a specific lease."""
    lease_id = request.query_params.get('lease_id')
    if not lease_id:
        return Response({"error": "lease_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        return Response({"error": "Lease not found."}, status=status.HTTP_404_NOT_FOUND)

    # Access control
    user = request.user
    if user.role == 'tenant' and hasattr(user, 'tenant') and lease.tenant != user.tenant:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'landlord' and hasattr(user, 'landlord_profile') and lease.property.landlord != user.landlord_profile:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    payments = Payment.objects.filter(lease=lease).order_by('-created_at')
    completed = payments.filter(status='COMPLETED')
    total_paid = sum(p.amount for p in completed)

    return Response({
        "lease_id": lease.id,
        "property": lease.property.title,
        "tenant": lease.tenant.full_name,
        "monthly_rent": float(lease.monthly_rent),
        "total_paid": float(total_paid),
        "balance_due": max(0, float(lease.monthly_rent) - float(total_paid)),
        "payment_count": payments.count(),
        "payments": PaymentSerializer(payments, many=True).data
    })


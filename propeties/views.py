from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.models import Property
from core.serializers import PropertySerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def public_property_list(request):
    """Public listing of all available properties."""
    properties = Property.objects.filter(status='AVAILABLE').order_by('-created_at')
    return Response({"properties": PropertySerializer(properties, many=True).data})


@api_view(['GET'])
@permission_classes([AllowAny])
def public_property_detail(request, pk):
    """Public detail view for a single property."""
    try:
        property_obj = Property.objects.get(pk=pk)
    except Property.DoesNotExist:
        return Response({"error": "Property not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(PropertySerializer(property_obj).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def property_stats(request):
    """Get property statistics (landlord/admin only)."""
    user = request.user

    if user.role == 'landlord' and hasattr(user, 'landlord_profile'):
        properties = Property.objects.filter(landlord=user.landlord_profile)
    elif user.role == 'admin':
        properties = Property.objects.all()
    else:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    total = properties.count()
    available = properties.filter(status='AVAILABLE').count()
    occupied = properties.filter(status='OCCUPIED').count()
    maintenance = properties.filter(status='MAINTENANCE').count()

    return Response({
        "total": total,
        "available": available,
        "occupied": occupied,
        "under_maintenance": maintenance,
        "occupancy_rate": round((occupied / total * 100) if total else 0, 2)
    })


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Property
from .serializers import PropertySerializer


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def property_api(request):
    if request.user.role != 'landlord':
        return Response({"error": "Only landlords are allowed"}, status=403)
    
    if request.method == 'GET':
        properties = request.user.landlord_profile.properties.all()
        serializer = PropertySerializer(properties, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = PropertySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(landlord=request.user.landlord_profile)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
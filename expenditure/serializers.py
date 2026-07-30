from rest_framework import serializers
from .models import Expenditure


class ExpenditureSerializer(serializers.ModelSerializer):
    """Serializer for recording and viewing expenses."""
    property_title = serializers.CharField(source='property.title', read_only=True)
    landlord_name = serializers.CharField(source='landlord.full_name', read_only=True)

    class Meta:
        model = Expenditure
        fields = [
            'id', 'title', 'category', 'amount', 'date_incurred',
            'property', 'property_title', 'landlord', 'landlord_name',
            'receipt', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'landlord', 'created_at', 'updated_at', 'property_title', 'landlord_name']


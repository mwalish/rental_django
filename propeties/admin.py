from django.contrib import admin
from core.models import Property


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    """Property management in admin panel."""
    list_display = ('title', 'landlord', 'location', 'rent_per_month', 'status')
    list_filter = ('status', 'has_water', 'has_electricity')
    search_fields = ('title', 'location', 'landlord__full_name')
    readonly_fields = ('created_at', 'updated_at')


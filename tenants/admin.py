from django.contrib import admin
from core.models import Tenant, RentalRequest, Maintenance


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """Tenant profile management in admin panel."""
    list_display = ('full_name', 'phone', 'id_number', 'email_address', 'join_date')
    list_filter = ('join_date',)
    search_fields = ('full_name', 'id_number', 'phone', 'email_address')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RentalRequest)
class RentalRequestAdmin(admin.ModelAdmin):
    """Rental applications from tenants."""
    list_display = ('property', 'tenant', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('tenant__full_name', 'property__title')


@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    """Maintenance requests submitted by tenants."""
    list_display = ('property', 'tenant', 'issue', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('issue', 'tenant__full_name', 'property__title')


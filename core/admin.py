from django.contrib import admin
from django.contrib.auth import get_user_model

# ✅ Import ALL models from the CORRECT place: landlord app
from .models import (
    Landlord,
    Tenant,
    Property,
    Lease,
    Payment,
    Maintenance,
    Notice
)

User = get_user_model()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'role', 'phone_number', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('email', 'username', 'phone_number')


@admin.register(Landlord)
class LandlordAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'id_number', 'business_name')
    search_fields = ('full_name', 'id_number', 'mpesa_number')


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'id_number', 'email_address')
    search_fields = ('full_name', 'id_number', 'email_address')


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'landlord', 'location', 'rent_per_month', 'status')
    list_filter = ('status', 'has_water', 'has_electricity')
    search_fields = ('title', 'location')


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ('property', 'tenant', 'start_date', 'end_date', 'status')
    list_filter = ('status',)
    search_fields = ('property__title', 'tenant__full_name')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('lease', 'amount', 'payment_date', 'method', 'status')
    list_filter = ('status', 'method')
    search_fields = ('transaction_id', 'lease__tenant__full_name')


@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('property', 'tenant', 'issue', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('issue', 'property__title')


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ('title', 'target', 'created_by', 'created_at')
    list_filter = ('target',)
    search_fields = ('title', 'message')
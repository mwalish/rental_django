from django.contrib import admin
from core.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Payment management in admin panel."""
    list_display = ('lease', 'amount', 'payment_date', 'method', 'status', 'transaction_id')
    list_filter = ('status', 'method', 'payment_date')
    search_fields = ('transaction_id', 'receipt_number', 'lease__tenant__full_name', 'lease__property__title')
    readonly_fields = ('created_at', 'updated_at', 'receipt_issued_at')
    date_hierarchy = 'payment_date'


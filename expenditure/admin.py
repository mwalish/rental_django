from django.contrib import admin
from .models import Expenditure


@admin.register(Expenditure)
class ExpenditureAdmin(admin.ModelAdmin):
    """Expenditure management in admin panel."""
    list_display = ('title', 'category', 'amount', 'date_incurred', 'landlord', 'property')
    list_filter = ('category', 'date_incurred')
    search_fields = ('title', 'notes', 'landlord__full_name', 'property__title')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'date_incurred'


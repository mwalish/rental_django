from django.urls import path
from . import views
from core import views as core_views

urlpatterns = [
    # Dashboard
    path("dashboard/", views.dashboard, name="landlord-dashboard"),

    # Profile
    path("profile/", views.profile, name="landlord-profile"),

    # Properties
    path("properties/", views.property_list, name="landlord-properties"),
    path("properties/<int:property_id>/applicants/", views.property_applicants, name="landlord-property-applicants"),
    path("properties/<int:pk>/", views.property_detail, name="landlord-property-detail"),

    # Rental Requests
    path("rental-requests/", views.rental_requests, name="landlord-rental-requests"),
    path("rental-requests/<int:pk>/", views.rental_requests, name="landlord-rental-request-detail"),
    path("rental-requests/<int:request_id>/convert-to-tenant/", views.convert_lead_to_tenant, name="landlord-request-convert-to-tenant"),

    # Meetings — ✅ Matches your working view names
    path("meetings/", views.meetings, name="landlord-meetings"),
    path("meetings/<int:pk>/", views.meeting_detail, name="landlord-meeting-detail"),

    # Leases
    path("leases/", views.lease_list_create, name="landlord-leases"),
    path("leases/<int:lease_id>/", views.lease_detail, name="landlord-lease-detail"),

    # Payments
    path("payments/", views.payments, name="landlord-payments"),
    path("payments/<int:pk>/", views.payment_detail, name="landlord-payment-detail"),

    # Tenants — list tenants linked to the landlord's properties
    path("tenants/", views.tenants, name="landlord-tenants"),
    path("registered-tenants/", views.registered_tenants, name="landlord-registered-tenants"),

    # Maintenance — reuses the role-aware core views (landlord-filtered)
    path("maintenance/", core_views.maintenance_list_create, name="landlord-maintenance"),
    path("maintenance/<int:maintenance_id>/", core_views.maintenance_detail, name="landlord-maintenance-detail"),
]

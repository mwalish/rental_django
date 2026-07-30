from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path("dashboard/", views.dashboard, name="landlord-dashboard"),

    # Profile
    path("profile/", views.profile, name="landlord-profile"),

    # Properties
    path("properties/", views.property_list, name="landlord-properties"),
    path("properties/<int:pk>/", views.property_detail, name="landlord-property-detail"),

    # Rental Requests
    path("rental-requests/", views.rental_requests, name="landlord-rental-requests"),
    path("rental-requests/<int:pk>/", views.rental_requests, name="landlord-rental-request-detail"),

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
]

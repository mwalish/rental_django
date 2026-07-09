from django.urls import path
from . import views

urlpatterns = [
    path("profile/", views.profile, name="landlord-profile"),
    path("properties/", views.property_list, name="landlord-properties"),
    path("properties/<int:pk>/", views.property_detail, name="landlord-property-detail"),
    path("rental-requests/", views.rental_requests, name="landlord-rental-requests"),
    path("rental-requests/<int:pk>/", views.rental_requests, name="landlord-rental-request-update"),
    path("meetings/", views.meetings, name="landlord-meetings"),
    path("leases/", views.leases, name="landlord-leases"),
    path("payments/", views.payments, name="landlord-payments"),
    path("dashboard/", views.dashboard, name="landlord-dashboard"),
]
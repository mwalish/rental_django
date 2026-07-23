# ==================================================
# URL Configuration — Property Management API
# ==================================================
from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

# Import class-based views explicitly
from .views import (
    AdminCreateLandlordView,
    LandlordCreateTenantView,
)

app_name = "core"

urlpatterns = [
    # ==============================================
    # Authentication & User Management
    # ==============================================
    path("register/", views.Register, name="register"),
    path("login/", views.Login, name="login"),
    path("profile/", views.ProfileView, name="profile"),
    path("logout/", views.logout_user, name="logout"),
    path("password/send-reset-code/", views.send_reset_code, name="send-reset-code"),
    path("password/confirm-reset/", views.confirm_password_reset, name="confirm-reset"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),

    path('admin/create-landlord/', AdminCreateLandlordView.as_view(), name='admin-create-landlord'),
    path('landlord/create-tenant/', LandlordCreateTenantView.as_view(), name='landlord-create-tenant'),

    # ==============================================
    # Rental Request Management
    # ==============================================
    path('rental-requests/', views.rental_request_list_create, name='rental-request-list-create'),
    path('rental-requests/<int:request_id>/', views.rental_request_detail, name='rental-request-detail'),

    # ==============================================
    # Meeting / Viewing Scheduling
    # ==============================================
    path('meetings/', views.meeting_list_create, name='meeting-list-create'),
    path('meetings/<int:meeting_id>/', views.meeting_detail, name='meeting-detail'),

    # ==============================================
    # Lease Management
    # ==============================================
    path('leases/', views.lease_list_create, name='lease_list_create'),
    path('leases/<int:lease_id>/', views.lease_detail, name='lease_detail'),

    # ==============================================
    # Notices & Announcements
    # ==============================================
    path('notices/', views.notice_list_create, name='notice_list_create'),
    path('notices/<int:notice_id>/', views.notice_detail, name='notice_detail'),

    # ==============================================
    # Maintenance Requests
    # ==============================================
    path('maintenance/', views.maintenance_list_create, name='maintenance_list_create'),
    path('maintenance/<int:maintenance_id>/', views.maintenance_detail, name='maintenance_detail'),

    # ==============================================
    # Payments & Financials
    # ==============================================
    path('payments/', views.payment_list_create, name='payment_list_create'),
    path('payments/<int:payment_id>/', views.payment_detail, name='payment_detail'),
    path('rent-for-month/', views.rent_for_month, name='rent-for-month'),
    path('payments/<int:payment_id>/verify/', views.verify_payment, name='verify-payment'),

    # ==============================================
    # Super Admin System Overview
    # ==============================================
    path('admin/dashboard/', views.admin_dashboard_stats, name='admin-dashboard'),
    path('admin/users/', views.admin_all_users, name='admin-all-users'),
]
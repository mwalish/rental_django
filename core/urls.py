from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import AdminCreateLandlordView, LandlordCreateTenantView
urlpatterns = [
    path("register/", views.Register, name="register"),
    path("login/", views.Login, name="login"),
    path("profile/", views.ProfileView, name="profile"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # Admin only endpoint
    path('admin/create-landlord/', AdminCreateLandlordView.as_view(), name='admin-create-landlord'),
    # Landlord only endpoint
    path('landlord/create-tenant/', LandlordCreateTenantView.as_view(), name='landlord-create-tenant'),
    # Lease routes
    path('leases/', views.lease_list_create, name='lease_list_create'),
    path('leases/<int:lease_id>/', views.lease_detail, name='lease_detail'),

    # --- NOTICE ROUTES ---
    path('notices/', views.notice_list_create, name='notice_list_create'),
    path('notices/<int:notice_id>/', views.notice_detail, name='notice_detail'),

    # --- MAINTENANCE ROUTES ---
    path('maintenance/', views.maintenance_list_create, name='maintenance_list_create'),
    path('maintenance/<int:maintenance_id>/', views.maintenance_detail, name='maintenance_detail'),

  

    # --- PAYMENT ROUTES ---
    path('payments/', views.payment_list_create, name='payment_list_create'),
    path('payments/<int:payment_id>/', views.payment_detail, name='payment_detail'),
    path('rent-for-month/', views.rent_for_month, name='rent-for-month'),


    # ✅ Super Admin Endpoints
    path('admin/dashboard/', views.admin_dashboard_stats, name='admin-dashboard'),
    path('admin/users/', views.admin_all_users, name='admin-all-users'),
]


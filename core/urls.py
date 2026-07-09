from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

urlpatterns = [
    path("register/", views.Register, name="register"),
    path("login/", views.Login, name="login"),
    path("profile/", views.ProfileView, name="profile"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    
    # Lease routes
    path('leases/', views.lease_list_create, name='lease_list_create'),
    path('leases/<int:lease_id>/', views.lease_detail, name='lease_detail'),

]
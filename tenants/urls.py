from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.my_profile, name='tenant-profile'),
    path('leases/', views.my_leases, name='tenant-leases'),

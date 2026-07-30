"""
URL configuration for rental project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Import core views for direct route aliasing
from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # API Schema & Swagger Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Core App Endpoints (auth, leases, payments, etc.)
    path("api/core/", include("core.urls")),

    # Landlord App Endpoints
    path("api/landlord/", include("landlord.urls")),

    # Direct alias for frontend — matches /api/properties/available/
    re_path(r'^api/properties/available/$', core_views.available_properties, name='available-properties-direct'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

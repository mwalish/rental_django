from django.urls import path
from . import views

urlpatterns = [
    path('public/', views.public_property_list, name='public-property-list'),
    path('public/<int:pk>/', views.public_property_detail, name='public-property-detail'),
    path('stats/', views.property_stats, name='property-stats'),
]

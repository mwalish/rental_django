from django.urls import path
from . import views

app_name = "expenditure"

urlpatterns = [
    path('', views.expense_list_create, name='expense-list-create'),
    path('<int:expense_id>/', views.expense_detail, name='expense-detail'),
]

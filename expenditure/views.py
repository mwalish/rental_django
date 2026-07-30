from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum

from .models import Expenditure
from .serializers import ExpenditureSerializer


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def expense_list_create(request):
    """List or create expenses. Landlords manage their own; admins see all."""
    user = request.user

    if request.method == 'POST':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Only landlords and admins can record expenses."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ExpenditureSerializer(data=request.data)
        if serializer.is_valid():
            if user.role == 'landlord' and hasattr(user, 'landlord_profile'):
                serializer.save(landlord=user.landlord_profile)
            elif user.role == 'admin':
                landlord_id = request.data.get('landlord')
                if not landlord_id:
                    return Response({"error": "Admin must specify landlord."}, status=status.HTTP_400_BAD_REQUEST)
                from core.models import Landlord
                try:
                    landlord = Landlord.objects.get(id=landlord_id)
                    serializer.save(landlord=landlord)
                except Landlord.DoesNotExist:
                    return Response({"error": "Landlord not found."}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({"error": "Cannot determine landlord."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Expense recorded.", "expense": serializer.data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # GET: List expenses
    if user.role == 'admin':
        expenses = Expenditure.objects.all().order_by('-date_incurred')
    elif user.role == 'landlord' and hasattr(user, 'landlord_profile'):
        expenses = Expenditure.objects.filter(landlord=user.landlord_profile).order_by('-date_incurred')
    else:
        return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

    total = expenses.aggregate(t=Sum('amount'))['t'] or 0
    return Response({
        "total_expenses": float(total),
        "expenses": ExpenditureSerializer(expenses, many=True).data
    })


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def expense_detail(request, expense_id):
    """View, update, or delete a single expense record."""
    user = request.user
    try:
        expense = Expenditure.objects.get(id=expense_id)
    except Expenditure.DoesNotExist:
        return Response({"error": "Expense not found."}, status=status.HTTP_404_NOT_FOUND)

    if user.role == 'landlord' and hasattr(user, 'landlord_profile') and expense.landlord != user.landlord_profile:
        return Response({"error": "You can only manage your own expenses."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response({"expense": ExpenditureSerializer(expense).data})
    if request.method == 'PUT':
        serializer = ExpenditureSerializer(expense, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Expense updated.", "expense": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        if user.role not in ['admin', 'landlord']:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        expense.delete()
        return Response({"message": "Expense deleted."})


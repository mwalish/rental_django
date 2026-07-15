from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.db.models import Sum,F
from datetime import datetime
from decimal import Decimal
# ✅ Import from core.models as you originally had
from .models import (
    User, Landlord, Tenant, Property, RentalRequest,
    Meeting, Lease, Payment, Maintenance, Notice
)
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User, Landlord, Tenant

# ------------------------------
# User Base Serializer
# ------------------------------
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'phone_number', 'role']
        read_only_fields = ['id']

# ------------------------------
# Admin creates Landlord
# ------------------------------
class LandlordCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'phone_number', 'password', 'password_confirm']

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        validate_password(data['password'])
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        # Set role automatically to landlord
        user = User.objects.create_user(role='landlord', **validated_data)
        # Create related Landlord profile
        Landlord.objects.create(user=user, full_name=user.username, phone=user.phone_number)
        return user

# ------------------------------
# Landlord creates Tenant
# ------------------------------
class TenantCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'phone_number', 'password', 'password_confirm']

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        validate_password(data['password'])
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        # Set role automatically to tenant
        user = User.objects.create_user(role='tenant', **validated_data)
        # Create related Tenant profile
        Tenant.objects.create(user=user, full_name=user.username, phone=user.phone_number, email_address=user.email)
        return user

# ---------------- USER & PROFILE SERIALIZERS ----------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'phone_number', 'password', 'password_confirm', 'role']
        extra_kwargs = {
            'username': {'required': False},
            'role': {'required': True}
        }

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already in use.")
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        validate_password(data['password'])
        return data


class LandlordProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Landlord
        fields = [
            "id", "full_name", "id_number", "phone", "mpesa_number",
            "address", "business_name", "license_number", "profile_picture",
            "created_at", "updated_at"
        ]
        read_only_fields = ["created_at", "updated_at"]


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = ["landlord", "created_at", "updated_at"]


class RentalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalRequest
        fields = "__all__"


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = "__all__"


class TenantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            'id', 'full_name', 'id_number', 'phone', 'alternative_phone',
            'email_address', 'join_date', 'exit_date', 'profile_picture',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['join_date', 'created_at', 'updated_at']

    def validate_id_number(self, value):
        if Tenant.objects.filter(id_number=value).exists():
            raise serializers.ValidationError("ID number already registered as tenant.")
        return value

    def validate_alternative_phone(self, value):
        if value and Tenant.objects.filter(alternative_phone=value).exists():
            raise serializers.ValidationError("Alternative phone number already in use.")
        return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'phone_number', 'role', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class LeaseSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source='property.title', read_only=True)
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)
    landlord_name = serializers.CharField(source='property.landlord.full_name', read_only=True)

    class Meta:
        model = Lease
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "property_title", "tenant_name", "landlord_name"]

    def validate(self, data):
        if data.get('end_date') and data.get('start_date') and data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({"end_date": "End date must be later than start date."})
        return data


# ------------------------------
# NOTICE SERIALIZER
# ------------------------------
class NoticeSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    created_by_role = serializers.CharField(source='created_by.role', read_only=True)

    class Meta:
        model = Notice
        fields = "__all__"
        read_only_fields = [
            "id", "created_by", "created_at", "updated_at",
            "created_by_name", "created_by_role"
        ]

# ------------------------------
# MAINTENANCE SERIALIZER
# ------------------------------
class MaintenanceSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source='property.title', read_only=True)
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)
    landlord_name = serializers.CharField(source='property.landlord.full_name', read_only=True)

    class Meta:
        model = Maintenance
        fields = "__all__"
        read_only_fields = [
            "id", "tenant", "created_at", "updated_at",
            "property_title", "tenant_name", "landlord_name"
        ]


# # ------------------------------
# PAYMENT SERIALIZER — 100% WORKING
# ------------------------------
from django.db.models import Sum
from decimal import Decimal  # ✅ Required for currency math

class PaymentSerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source='lease.property.title', read_only=True)
    tenant_name = serializers.CharField(source='lease.tenant.full_name', read_only=True)
    landlord_name = serializers.CharField(source='lease.property.landlord.full_name', read_only=True)
    lease_monthly_rent = serializers.DecimalField(source='lease.monthly_rent', max_digits=12, decimal_places=2, read_only=True)
    covers_months = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = [
            "id", "payment_date", "created_at", "updated_at",
            "property_title", "tenant_name", "landlord_name", "lease_monthly_rent", "covers_months"
        ]

    def get_covers_months(self, obj):
        if hasattr(obj, 'covered_months') and obj.covered_months:
            return obj.covered_months
        return "Pending assignment"

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, data):
        lease = data.get('lease') or getattr(self.instance, 'lease', None)
        if not lease:
            return data

        request = self.context.get('request')
        user_role = request.user.role if request else None

        # ✅ Admin/Landlord are always exempt
        if user_role in ['admin', 'landlord']:
            return data

        # ✅ Count ONLY completed payments for THIS exact lease
        total_completed = Payment.objects.filter(
            lease=lease,
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # ✅ Allow FIRST payment ever — no false block for new leases
        if total_completed == Decimal('0'):
            return data

        # ✅ Fixed Decimal math — no type errors!
        outstanding = max(Decimal('0'), lease.monthly_rent - total_completed)
        if outstanding > Decimal('0'):
            raise serializers.ValidationError({
                "error": f"You cannot pay rent for this month until you clear the outstanding balance of KSh {outstanding:.2f} from the previous month.",
                "current_balance_due": f"{outstanding:.2f}"
            })

        return data
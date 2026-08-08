"""
==========================================
Core Serializers — Validation & Data Conversion
==========================================
All serializers for the core app live here:
- User auth & registration serializers
- Profile serializers (Landlord, Tenant)
- Business model serializers (Property, Lease, Payment, etc.)
- Each serializer enforces role-based validation rules
==========================================
"""
from jsonschema import ValidationError
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.db.models import Sum
from decimal import Decimal

from .models import (
    User, Landlord, Tenant, Property, RentalRequest,
    Meeting, Lease, Payment, Maintenance, Notice
)


# ==================================================
# User & Authentication Serializers
# ==================================================
class UserSerializer(serializers.ModelSerializer):
    """Basic read/write serializer for User account data (excludes password)."""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'phone_number', 'role', 'date_joined', 'full_name', 'profile_picture']
        read_only_fields = ['id', 'date_joined']

    def get_full_name(self, obj):
        # The User model has no 'full_name' field — use getattr to be safe.
        # The full name lives on the linked Landlord/Tenant profile instead.
        if getattr(obj, 'full_name', None):
            return obj.full_name
        # Fall back to linked profile's full_name if present
        if hasattr(obj, 'landlord_profile') and obj.landlord_profile.full_name:
            return obj.landlord_profile.full_name
        if hasattr(obj, 'tenant') and obj.tenant.full_name:
            return obj.tenant.full_name
        return obj.username


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Registration serializer — validates unique email/phone, password match, and strength."""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'phone_number', 'password', 'password_confirm', 'role']
        extra_kwargs = {'username': {'required': False}, 'role': {'required': True}}

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


class LandlordCreateSerializer(serializers.ModelSerializer):
    """Admin-only: creates a User with landlord role + auto-creates Landlord profile."""
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
        user = User.objects.create_user(role='landlord', **validated_data)
        Landlord.objects.create(user=user, full_name=user.username, phone=user.phone_number)
        return user


class TenantCreateSerializer(serializers.ModelSerializer):
    """Landlord-only: creates a User with tenant role + full Tenant profile with all details."""
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True, required=True, min_length=6)
    full_name = serializers.CharField(required=True, max_length=100)
    id_number = serializers.CharField(required=True, max_length=20)
    phone = serializers.CharField(required=True, max_length=20)
    email_address = serializers.EmailField(required=False, allow_blank=True)
    alternative_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'email', 'username', 'phone_number', 'password', 'password_confirm',
            'full_name', 'id_number', 'phone', 'email_address', 'alternative_phone'
        ]

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return data

    def create(self, validated_data):
        profile_data = {
            'full_name': validated_data.pop('full_name'),
            'id_number': validated_data.pop('id_number'),
            'phone': validated_data.pop('phone'),
            'email_address': validated_data.pop('email_address', validated_data.get('email')),
            'alternative_phone': validated_data.pop('alternative_phone', None)
        }
        validated_data.pop('password_confirm')
        user = User.objects.create_user(role='tenant', **validated_data)

        # If the request came from a landlord, track who registered this tenant
        landlord = self.context.get('landlord') if hasattr(self, 'context') else None
        if landlord is None:
            request = self.context.get('request') if hasattr(self, 'context') else None
            if request and getattr(request.user, 'role', None) == 'landlord' and hasattr(request.user, 'landlord_profile'):
                landlord = request.user.landlord_profile
        if landlord is not None:
            profile_data['registered_by'] = landlord

        return Tenant.objects.create(user=user, **profile_data)


# ==================================================
# Profile Serializers
# ==================================================
class LandlordProfileSerializer(serializers.ModelSerializer):
    """Full read/write for Landlord business details, M-Pesa number, and documents."""
    class Meta:
        model = Landlord
        fields = [
            "id", "full_name", "id_number", "phone", "mpesa_number",
            "address", "business_name", "license_number", "profile_picture",
            "created_at", "updated_at"
        ]
        read_only_fields = ["created_at", "updated_at"]


class TenantProfileSerializer(serializers.ModelSerializer):
    """Full read/write for Tenant profile — validates unique ID and contact numbers.

    Includes derived display fields so landlords/admins can see the tenant's
    login email and who registered them (useful for the tenants list & detail).
    """
    user_email = serializers.EmailField(source='user.email', read_only=True, allow_null=True)
    registered_by_name = serializers.CharField(source='registered_by.full_name', read_only=True, allow_null=True)
    status = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Tenant
        fields = [
            'id', 'full_name', 'id_number', 'phone', 'alternative_phone',
            'email_address', 'join_date', 'exit_date', 'profile_picture',
            'created_at', 'updated_at',
            'user_email', 'registered_by_name', 'status'
        ]
        read_only_fields = ['join_date', 'created_at', 'updated_at']

    def get_status(self, obj):
        return 'ACTIVE' if getattr(obj.user, 'is_active', True) else 'INACTIVE'

    def validate_id_number(self, value):
        if Tenant.objects.filter(id_number=value).exists():
            raise serializers.ValidationError("ID number already registered as tenant.")
        return value

    def validate_alternative_phone(self, value):
        if value and Tenant.objects.filter(alternative_phone=value).exists():
            raise serializers.ValidationError("Alternative phone number already in use.")
        return value


# ==================================================
# Core Business Serializers
# ==================================================
class PropertySerializer(serializers.ModelSerializer):
    """Property listings — landlord is auto-set from authenticated user.
    Includes landlord contact details so the house-hunting portal shows
    real owner info on each listing.
    Now supports multiple photos via the `photos` JSONField (array of base64 strings).
    """
    landlord_name = serializers.CharField(source='landlord.full_name', read_only=True)
    landlord_phone = serializers.CharField(source='landlord.phone', read_only=True)
    landlord_email = serializers.EmailField(source='landlord.user.email', read_only=True, allow_null=True)
    landlord_business = serializers.CharField(source='landlord.business_name', read_only=True, allow_null=True)

    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = ["landlord", "created_at", "updated_at"]


class RentalRequestSerializer(serializers.ModelSerializer):
    """Tenant rental applications — includes display names for UI convenience.

    Supports guest/lead inquiries where no tenant account exists: applicant
    contact info is stored in lead_name / lead_phone / lead_email instead.

    Also exposes the linked tenant's profile contact details (phone, email,
    ID number) so the landlord can see who applied for their houses.
    """
    tenant_name = serializers.SerializerMethodField(read_only=True)
    tenant_phone = serializers.CharField(source='tenant.phone', read_only=True, allow_null=True)
    tenant_email = serializers.EmailField(source='tenant.email_address', read_only=True, allow_null=True)
    tenant_id_number = serializers.CharField(source='tenant.id_number', read_only=True, allow_null=True)
    landlord_name = serializers.CharField(source='landlord.full_name', read_only=True)
    property_title = serializers.CharField(source='property.title', read_only=True)
    property_location = serializers.CharField(source='property.location', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RentalRequest
        fields = [
            'id', 'property', 'property_title', 'property_location',
            'tenant', 'tenant_name', 'tenant_phone', 'tenant_email', 'tenant_id_number',
            'landlord', 'landlord_name',
            'lead_name', 'lead_phone', 'lead_email',
            'message', 'landlord_notes', 'status', 'status_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant', 'landlord', 'created_at', 'updated_at',
            'tenant_name', 'tenant_phone', 'tenant_email', 'tenant_id_number',
            'landlord_name', 'property_title', 'property_location', 'status_display'
        ]

    def get_tenant_name(self, obj):
        """Return linked tenant's full name, falling back to guest lead name."""
        if obj.tenant:
            return obj.tenant.full_name
        return obj.lead_name


class MeetingSerializer(serializers.ModelSerializer):
    """Property viewing/meeting scheduler — includes formatted date and related names."""
    landlord_name = serializers.SerializerMethodField(read_only=True)
    tenant_name = serializers.SerializerMethodField(read_only=True)
    property_title = serializers.SerializerMethodField(read_only=True)
    date_time_formatted = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id', 'date_time', 'date_time_formatted', 'notes', 'status',
            'created_at', 'landlord', 'landlord_name', 'property', 'property_title', 'tenant', 'tenant_name'
        ]
        read_only_fields = ['id', 'created_at', 'landlord', 'landlord_name']

    def get_landlord_name(self, obj):
        try: return obj.landlord.full_name
        except: return None
    def get_tenant_name(self, obj):
        try: return obj.tenant.full_name
        except: return None
    def get_property_title(self, obj):
        try: return obj.property.title
        except: return None
    def get_date_time_formatted(self, obj):
        try: return obj.date_time.strftime("%d %B %Y, %H:%M")
        except: return None


class LeaseSerializer(serializers.ModelSerializer):
    """Lease agreements — validates end date > start date; includes cross-linked names."""
    property_title = serializers.CharField(source='property.title', read_only=True)
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)
    landlord_name = serializers.CharField(source='property.landlord.full_name', read_only=True)

    class Meta:
        model = Lease
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "property_title", "tenant_name", "landlord_name"]

    def validate(self, data):
        from datetime import date as _date_import

        # Resolve dates: use incoming values, or fall back to existing instance values
        # for partial updates (so editing unrelated fields still validates correctly).
        start = data.get('start_date') or (getattr(self.instance, 'start_date', None) if self.instance else None)
        end = data.get('end_date') or (getattr(self.instance, 'end_date', None) if self.instance else None)

        if not start:
            raise serializers.ValidationError({"start_date": "Start date is required."})
        if not end:
            raise serializers.ValidationError({"end_date": "End date is required."})

        # Enforce end date strictly after start date.
        if end <= start:
            raise serializers.ValidationError({"end_date": "End date must be later than start date."})

        # On CREATE only, reject a start date in the past.
        if not self.instance and start < _date_import.today():
            raise serializers.ValidationError({"start_date": "Start date cannot be in the past."})

        return data


class NoticeSerializer(serializers.ModelSerializer):
    """System announcements — tracks author and target audience."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    created_by_role = serializers.CharField(source='created_by.role', read_only=True)

    class Meta:
        model = Notice
        fields = "__all__"
        read_only_fields = [
            "id", "created_by", "created_at", "updated_at",
            "created_by_name", "created_by_role"
        ]


class MaintenanceSerializer(serializers.ModelSerializer):
    """Maintenance requests — links property, reporter, and owner."""
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


class PaymentSerializer(serializers.ModelSerializer):
    """Rent payments — validates amounts, tracks receipts, enforces outstanding balance rules."""
    property_title = serializers.CharField(
        source='lease.property.title', read_only=True,
        help_text="Name of the property for this payment"
    )
    tenant_name = serializers.CharField(
        source='lease.tenant.full_name', read_only=True,
        help_text="Full name of the tenant making the payment"
    )
    landlord_name = serializers.CharField(
        source='lease.property.landlord.full_name', read_only=True,
        help_text="Name of the property owner/landlord"
    )
    lease_monthly_rent = serializers.DecimalField(
        source='lease.monthly_rent', max_digits=12, decimal_places=2, read_only=True,
        help_text="Monthly rent amount from the linked lease"
    )
    covers_months = serializers.SerializerMethodField(
        help_text="Months covered by this payment"
    )

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = [
            "id", "payment_date", "created_at", "updated_at",
            "property_title", "tenant_name", "landlord_name", "lease_monthly_rent", "covers_months",
            "receipt_number", "receipt_issued_at", "issued_by", "balance_after_payment"
        ]

    def get_covers_months(self, obj):
        """Return covered months or a friendly default if empty."""
        return getattr(obj, 'covered_months', "Pending assignment")

    def validate_amount(self, value):
        """Reject zero or negative payment amounts."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, data):
        """
        Prevent tenants from paying new periods if outstanding balance exists.
        Admins and landlords are exempt from this check.
        """
        lease = data.get('lease') or getattr(self.instance, 'lease', None)
        if not lease:
            return data

        request = self.context.get('request')
        user_role = request.user.role if request else None

        if user_role in ['admin', 'landlord']:
            return data

        total_completed = Payment.objects.filter(
            lease=lease, status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        if total_completed == Decimal('0'):
            return data

        outstanding = max(Decimal('0'), lease.monthly_rent - total_completed)
        if outstanding > Decimal('0'):
            raise serializers.ValidationError({
                "error": f"Clear outstanding balance of KSh {outstanding:.2f} before paying new periods.",
                "current_balance_due": f"{outstanding:.2f}"
            })
        return data

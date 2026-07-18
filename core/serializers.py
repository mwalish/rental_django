# ==================================================
# Imports — Cleaned & Deduplicated
# ==================================================
"""
Shared utilities and model imports for all serializers in the core app.
All serializers follow consistent naming, validation, and permission patterns.
"""
from jsonschema import ValidationError
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.db.models import Sum, F
from datetime import datetime
from decimal import Decimal

# Core application models — update here if model names change
from .models import (
    User, Landlord, Tenant, Property, RentalRequest,
    Meeting, Lease, Payment, Maintenance, Notice
)


# ==================================================
# User & Authentication Serializers
# ==================================================
class UserSerializer(serializers.ModelSerializer):
    """
    Basic read/write serializer for core User account data.
    Used across all roles for displaying minimal user identity info.
    Excludes sensitive fields like password.
    """
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'phone_number', 'role', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Public self-registration serializer for all user roles.
    Enforces unique email/phone checks, password matching, and role selection.
    Creates a core User record only — linked profiles are created separately.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="Secure password (min 8 chars, mixed chars)")
    password_confirm = serializers.CharField(write_only=True, required=True, help_text="Re-enter password to confirm")

    class Meta:
        model = User
        fields = ['email', 'username', 'phone_number', 'password', 'password_confirm', 'role']
        extra_kwargs = {
            'username': {'required': False, 'help_text': 'Optional display name (defaults to email prefix)'},
            'role': {'required': True, 'help_text': 'Account type: admin/landlord/tenant'}
        }

    def validate_email(self, value):
        """Normalize email to lowercase and prevent duplicate registrations"""
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_phone_number(self, value):
        """Ensure phone number is not linked to another account"""
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already in use.")
        return value

    def validate(self, data):
        """Check that both entered passwords match"""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        validate_password(data['password'])
        return data


class LandlordCreateSerializer(serializers.ModelSerializer):
    """
    Admin-only serializer to create new Landlord accounts.
    Automatically sets role=landlord and creates linked Landlord profile.
    Used only by admin dashboard — not for public signups.
    """
    password = serializers.CharField(write_only=True, required=True, help_text="Landlord account password")
    password_confirm = serializers.CharField(write_only=True, required=True, help_text="Confirm password")

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
        # Create core user account with landlord role
        user = User.objects.create_user(role='landlord', **validated_data)
        # Auto-create matching Landlord profile
        Landlord.objects.create(user=user, full_name=user.username, phone=user.phone_number)
        return user


# class TenantCreateSerializer(serializers.ModelSerializer):
#     """
#     Landlord-only serializer to create new Tenant accounts.
#     Automatically sets role=tenant and creates linked Tenant profile.
#     Used when landlords add tenants directly to their properties.
#     """
#     password = serializers.CharField(write_only=True, required=True, help_text="Tenant account password")
#     password_confirm = serializers.CharField(write_only=True, required=True, help_text="Confirm password")

#     class Meta:
#         model = User
#         fields = ['email', 'username', 'phone_number', 'password', 'password_confirm']

#     def validate(self, data):
#         if data['password'] != data['password_confirm']:
#             raise serializers.ValidationError({"password": "Passwords do not match."})
#         validate_password(data['password'])
#         return data

#     def create(self, validated_data):
#         validated_data.pop('password_confirm')
#         # Create core user account with tenant role
#         user = User.objects.create_user(role='tenant', **validated_data)
#         # Auto-create matching Tenant profile
#         Tenant.objects.create(user=user, full_name=user.username, phone=user.phone_number, email_address=user.email)
#         return user
class TenantCreateSerializer(serializers.ModelSerializer):
    """
    Landlord-only serializer to create new Tenant accounts.
    Automatically creates User + linked Tenant profile with all details.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=6,
        help_text="Tenant account password"
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        min_length=6,
        help_text="Confirm password"
    )

    # Tenant profile extra fields
    full_name = serializers.CharField(required=True, max_length=100)
    id_number = serializers.CharField(required=True, max_length=20)
    phone = serializers.CharField(required=True, max_length=20)
    email_address = serializers.EmailField(required=False, allow_blank=True)
    alternative_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'email', 'username', 'phone_number',
            'password', 'password_confirm',
            'full_name', 'id_number', 'phone',
            'email_address', 'alternative_phone'
        ]

    def validate(self, data):
        # Match passwords
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        
        # Validate password strength
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        
        return data

    def create(self, validated_data):
        # Extract profile fields NOT part of User model
        profile_data = {
            'full_name': validated_data.pop('full_name'),
            'id_number': validated_data.pop('id_number'),
            'phone': validated_data.pop('phone'),
            'email_address': validated_data.pop('email_address', validated_data.get('email')),
            'alternative_phone': validated_data.pop('alternative_phone', None)
        }

        # Remove confirm password before creating user
        validated_data.pop('password_confirm')

        # Create User with tenant role
        user = User.objects.create_user(
            role='tenant',
            **validated_data
        )

        # Create full Tenant profile with all details
        tenant = Tenant.objects.create(
            user=user,
            **profile_data
        )

        return tenant


# ==================================================
# Profile Serializers
# ==================================================
class LandlordProfileSerializer(serializers.ModelSerializer):
    """
    Full read/write serializer for Landlord profile details.
    Includes business info, payment details, and documents.
    Timestamps are auto-managed and read-only.
    """
    class Meta:
        model = Landlord
        fields = [
            "id", "full_name", "id_number", "phone", "mpesa_number",
            "address", "business_name", "license_number", "profile_picture",
            "created_at", "updated_at"
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "mpesa_number": {"help_text": "Safaricom M-Pesa number for rent collections"},
            "license_number": {"help_text": "Optional: Property management license ID"}
        }


class TenantProfileSerializer(serializers.ModelSerializer):
    """
    Full read/write serializer for Tenant profile details.
    Validates unique ID and contact numbers to avoid duplicates.
    Join/exit dates are managed via lease records, not manual edits.
    """
    class Meta:
        model = Tenant
        fields = [
            'id', 'full_name', 'id_number', 'phone', 'alternative_phone',
            'email_address', 'join_date', 'exit_date', 'profile_picture',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['join_date', 'created_at', 'updated_at']
        extra_kwargs = {
            "alternative_phone": {"help_text": "Optional emergency contact number"}
        }

    def validate_id_number(self, value):
        """Prevent duplicate national ID registration"""
        if Tenant.objects.filter(id_number=value).exists():
            raise serializers.ValidationError("ID number already registered as tenant.")
        return value

    def validate_alternative_phone(self, value):
        """Ensure alternative contact is not already in use"""
        if value and Tenant.objects.filter(alternative_phone=value).exists():
            raise serializers.ValidationError("Alternative phone number already in use.")
        return value


# ==================================================
# Core Business Serializers
# ==================================================
class PropertySerializer(serializers.ModelSerializer):
    """
    Full serializer for property listings and details.
    Landlord is set automatically from the logged-in user — cannot be edited manually.
    Used for listing, filtering, and property management.
    """
    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = ["landlord", "created_at", "updated_at"]
        extra_kwargs = {
            "rent_amount": {"help_text": "Monthly rent in KSh"},
            "status": {"help_text": "Available/Rented/Maintenance"}
        }


class RentalRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for tenant rental applications and landlord reviews.
    Auto-links landlord from property, prevents duplicate pending requests.
    Includes formatted display values for UI convenience.
    """
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True, help_text="Full name of applicant")
    landlord_name = serializers.CharField(source='landlord.full_name', read_only=True, help_text="Property owner name")
    property_title = serializers.CharField(source='property.title', read_only=True, help_text="Name/title of applied property")
    property_location = serializers.CharField(source='property.location', read_only=True, help_text="Property location")
    status_display = serializers.CharField(source='get_status_display', read_only=True, help_text="Human-readable status label")

    class Meta:
        model = RentalRequest
        fields = [
            'id', 'property', 'property_title', 'property_location',
            'tenant', 'tenant_name', 'landlord', 'landlord_name',
            'message', 'landlord_notes', 'status', 'status_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant', 'landlord', 'created_at', 'updated_at',
            'tenant_name', 'landlord_name', 'property_title', 'property_location', 'status_display'
        ]
        extra_kwargs = {
            "message": {"help_text": "Tenant's note about their interest or requirements"},
            "landlord_notes": {"help_text": "Owner feedback when approving or rejecting"}
        }


class MeetingSerializer(serializers.ModelSerializer):
    """
    Serializer for scheduling and managing landlord-tenant meetings/viewings.
    Supports meetings for new tenants (no existing tenant ID) or existing tenants.
    Includes formatted date for direct frontend display.
    """
    landlord_name = serializers.CharField(source='landlord.full_name', read_only=True, help_text="Host/landlord name")
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True, allow_null=True, help_text="Attending tenant name (null for new enquiries)")
    property_title = serializers.CharField(source='property.title', read_only=True, help_text="Property to meet about")
    date_time_formatted = serializers.DateTimeField(source='date_time', format="%d %B %Y, %H:%M", read_only=True, help_text="Readable local date/time")

    class Meta:
        model = Meeting
        fields = [
            'id', 'date_time', 'date_time_formatted', 'notes', 'status',
            'created_at', 'landlord', 'landlord_name', 'property', 'property_title',
            'tenant', 'tenant_name'
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            "notes": {"help_text": "Meeting agenda, location, or special instructions"}
        }


class LeaseSerializer(serializers.ModelSerializer):
    """
    Serializer for formal tenancy lease agreements.
    Validates date logic to ensure end date comes after start date.
    Includes cross-linked names for quick reference.
    """
    property_title = serializers.CharField(source='property.title', read_only=True, help_text="Leased property name")
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True, help_text="Tenant under agreement")
    landlord_name = serializers.CharField(source='property.landlord.full_name', read_only=True, help_text="Lease issuer/owner")

    class Meta:
        model = Lease
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "property_title", "tenant_name", "landlord_name"]
        extra_kwargs = {
            "rent_amount": {"help_text": "Agreed monthly rent"},
            "deposit": {"help_text": "Security deposit amount"}
        }

    def validate(self, data):
        """Ensure lease end date is strictly after start date"""
        if data.get('end_date') and data.get('start_date') and data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({"end_date": "End date must be later than start date."})
        return data


class NoticeSerializer(serializers.ModelSerializer):
    """
    Serializer for system-wide or targeted notices/announcements.
    Tracks who created the notice and their role for audit purposes.
    """
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, help_text="Author full name")
    created_by_role = serializers.CharField(source='created_by.role', read_only=True, help_text="Author account role")

    class Meta:
        model = Notice
        fields = "__all__"
        read_only_fields = [
            "id", "created_by", "created_at", "updated_at",
            "created_by_name", "created_by_role"
        ]
        extra_kwargs = {
            "is_public": {"help_text": "Visible to all users or targeted only"}
        }


class MaintenanceSerializer(serializers.ModelSerializer):
    """
    Serializer for reporting and managing property maintenance requests.
    Links directly to the affected property, reporter, and property owner.
    """
    property_title = serializers.CharField(source='property.title', read_only=True, help_text="Property with the issue")
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True, help_text="Reporter/tenant name")
    landlord_name = serializers.CharField(source='property.landlord.full_name', read_only=True, help_text="Responsible owner")

    class Meta:
        model = Maintenance
        fields = "__all__"
        read_only_fields = [
            "id", "tenant", "created_at", "updated_at",
            "property_title", "tenant_name", "landlord_name"
        ]
        extra_kwargs = {
            "priority": {"help_text": "Low/Medium/High/Emergency"},
            "description": {"help_text": "Detailed description of the fault or repair needed"}
        }


class PaymentSerializer(serializers.ModelSerializer):
    """
    Full payment serializer with validation, receipt tracking, and balance checks.
    Prevents partial carry-over payments for tenants with outstanding balances.
    Auto-generates receipt details and final balance for every transaction.
    """
    property_title = serializers.CharField(source='lease.property.title', read_only=True, help_text="Property being paid for")
    tenant_name = serializers.CharField(source='lease.tenant.full_name', read_only=True, help_text="Payer name")
    landlord_name = serializers.CharField(source='lease.property.landlord.full_name', read_only=True, help_text="Payment recipient")
    lease_monthly_rent = serializers.DecimalField(source='lease.monthly_rent', max_digits=12, decimal_places=2, read_only=True, help_text="Agreed monthly rent amount")
    covers_months = serializers.SerializerMethodField(help_text="Period covered by this payment")

    receipt_number = serializers.CharField(read_only=True, help_text="System-generated unique receipt ID")
    receipt_issued_at = serializers.DateTimeField(read_only=True, help_text="Exact time receipt was issued")
    balance_after_payment = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, help_text="Remaining balance after this transaction")

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = [
            "id", "payment_date", "created_at", "updated_at",
            "property_title", "tenant_name", "landlord_name", "lease_monthly_rent", "covers_months",
            "receipt_number", "receipt_issued_at", "balance_after_payment"
        ]
        extra_kwargs = {
            "method": {"help_text": "M-Pesa/Bank/Cash"},
            "transaction_ref": {"help_text": "Payment provider reference code"}
        }

    def get_covers_months(self, obj):
        """Return period covered or pending status if not yet allocated"""
        if hasattr(obj, 'covered_months') and obj.covered_months:
            return obj.covered_months
        return "Pending assignment"

    def validate_amount(self, value):
        """Reject zero or negative payment amounts"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, data):
        """
        Enforce outstanding balance rule:
        - Admins/landlords are exempt from this check
        - New leases allow first payment without restrictions
        - Tenants with unpaid balances must clear them before paying new periods
        """
        lease = data.get('lease') or getattr(self.instance, 'lease', None)
        if not lease:
            return data

        request = self.context.get('request')
        user_role = request.user.role if request else None

        # Skip check for privileged users
        if user_role in ['admin', 'landlord']:
            return data

        # Sum all completed payments for this specific lease only
        total_completed = Payment.objects.filter(
            lease=lease,
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Allow first payment for new leases
        if total_completed == Decimal('0'):
            return data

        # Block new payments if previous balance is unpaid
        outstanding = max(Decimal('0'), lease.monthly_rent - total_completed)
        if outstanding > Decimal('0'):
            raise serializers.ValidationError({
                "error": f"You cannot pay rent for this month until you clear the outstanding balance of KSh {outstanding:.2f} from the previous month.",
                "current_balance_due": f"{outstanding:.2f}"
            })

        return data
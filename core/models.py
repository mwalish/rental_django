"""
==========================================
Core Models — Smart Rental Management System
==========================================
This module defines ALL database models for the rental system:
- User (custom auth), Landlord, Tenant profiles
- Property, Lease, Payment, Maintenance
- RentalRequest, Meeting, Notice, PasswordResetCode

All business logic models are centralized here to avoid duplication.
The landlord app and other modules import from here.
==========================================
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal
from datetime import datetime

# ------------------------------------------------------
# Custom User Model (extends Django's AbstractUser)
# ----------------------------------------------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'System Admin'),
        ('landlord', 'Landlord / Owner'),
        ('tenant', 'Tenant'),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='tenant')
    phone_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(max_length=50, unique=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)

    # Fix reverse accessor conflict with Django auth
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='core_user_groups',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='core_user_perms',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'phone_number']

    @property
    def full_name(self):
        """Full display name for any user (admin/landlord/tenant).

        The User model has no dedicated 'full_name' DB column — the full name
        lives on the linked Landlord/Tenant profile for those roles. For admins
        (and any user without a linked profile) we build the name from the
        inherited first_name/last_name, falling back to the username so this
        property ALWAYS resolves without raising an AttributeError.
        """
        name = " ".join(part for part in (self.first_name, self.last_name) if part).strip()
        return name or self.username

    @full_name.setter
    def full_name(self, value):
        """Store the admin's full name on the inherited first_name column.

        This lets callers do `user.full_name = "<name>"` and have it persisted
        to the database (first_name + last_name) instead of being silently lost.
        """
        value = (value or "").strip()
        parts = value.split()
        self.first_name = parts[0] if parts else ""
        self.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    def __str__(self):
        return f"{self.username} ({self.role})"


# ----------------------------------------------------------------------
# Password Reset Code Model — stores 6-digit codes for password recovery
# ----------------------------------------------------------------------
class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"Reset for {self.user.username} | Expires: {self.expires_at}"


# ------------------------------
# Landlord Profile Model — linked 1-to-1 with User; stores business & ID details
# ------------------------------
class Landlord(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='landlord_profile')
    full_name = models.CharField(max_length=100)
    id_number = models.CharField(max_length=30, unique=True)
    mpesa_number = models.CharField(max_length=15)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    business_name = models.CharField(max_length=100, blank=True, null=True)
    license_number = models.CharField(max_length=50, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='landlords/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name


# ------------------------------
# Tenant Profile Model — linked 1-to-1 with User; stores personal & contact info
# ------------------------------
class Tenant(models.Model):
    full_name = models.CharField(max_length=100)
    id_number = models.CharField(max_length=20, unique=True)
    phone = models.CharField(max_length=20)
    email_address = models.EmailField(blank=True, null=True)
    alternative_phone = models.CharField(max_length=20, blank=True, null=True)
    join_date = models.DateField(null=True, blank=True, verbose_name="Tenant Join Date")
    exit_date = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to="tenants/", blank=True, null=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tenant")
    registered_by = models.ForeignKey(
        'Landlord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registered_tenants',
        help_text="Landlord who registered this tenant (null for self-registered)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

# ------------------------------
# Property Model — rental units owned by landlords; tracks status, rent, amenities
# ------------------------------
class Property(models.Model):
    STATUS_CHOICES = (
        ('AVAILABLE', 'Available'),
        ('OCCUPIED', 'Occupied'),
        ('MAINTENANCE', 'Under Maintenance'),
    )
    title = models.CharField(max_length=100)
    landlord = models.ForeignKey(Landlord, on_delete=models.CASCADE, related_name='properties')
    location = models.CharField(max_length=255)
    rent_per_month = models.DecimalField(max_digits=10, decimal_places=2)
    bedrooms = models.PositiveIntegerField(default=1, help_text="Number of bedrooms")
    bathrooms = models.PositiveIntegerField(default=1, help_text="Number of bathrooms")
    square_feet = models.PositiveIntegerField(null=True, blank=True, help_text="Property size in square feet")
    has_water = models.BooleanField(default=True)
    has_electricity = models.BooleanField(default=True)
    photos = models.JSONField(default=list, blank=True, help_text="Array of base64 image strings for property photos")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


# ------------------------------
# Rental Request Model — tenants apply to rent a property; landlords approve/reject
# ------------------------------
class RentalRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='rental_requests',
        help_text="Property the tenant is applying for"
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rental_applications',
        help_text="Tenant submitting the request (null for guest/lead inquiries)"
    )
    landlord = models.ForeignKey(
        Landlord,
        on_delete=models.CASCADE,
        related_name='incoming_requests',
        editable=False,
        help_text="Auto-set from property owner"
    )
    # Guest/lead contact fields — used when a visitor without a tenant account
    # submits a rental inquiry directly (no sign-up required).
    lead_name = models.CharField(max_length=100, blank=True, null=True, help_text="Full name from guest inquiry")
    lead_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number from guest inquiry")
    lead_email = models.EmailField(blank=True, null=True, help_text="Email from guest inquiry")
    message = models.TextField(blank=True, null=True, help_text="Tenant's application note")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    landlord_notes = models.TextField(blank=True, null=True, help_text="Landlord feedback")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['property', 'tenant']
        verbose_name = "Rental Request"
        verbose_name_plural = "Rental Requests"

    def __str__(self):
        return f"Request: {self.property.title} ↔ {self.tenant.full_name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.landlord_id:
            self.landlord = self.property.landlord
        super().save(*args, **kwargs)


# ------------------------------
# Meeting / Viewing Model — schedules property viewings between landlords and tenants
# ------------------------------
class Meeting(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SCHEDULED', 'Scheduled'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    landlord = models.ForeignKey(Landlord, on_delete=models.CASCADE, related_name='meetings')
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name='meetings')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='meetings')
    date_time = models.DateTimeField(help_text="Date and time of the meeting/viewing")
    notes = models.TextField(blank=True, null=True, help_text="Agenda or special instructions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Meeting: {self.property.title} — {self.date_time.strftime('%Y-%m-%d %H:%M')}"


# ------------------------------
# Lease Agreement Model — binds tenant to property for a period with monthly rent
# ------------------------------
class Lease(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='leases')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leases')
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('TERMINATED', 'Terminated'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Lease: {self.property.title} - {self.tenant.full_name}"


# ------------------------------
# Payment Model — rent transactions; tracks M-Pesa, bank, cash, cheque, receipts, balances
# ------------------------------
class Payment(models.Model):
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)

    # ✅ BACK TO "method" — matches your Admin perfectly
    PAYMENT_METHODS = (
        ('M-Pesa', 'M-Pesa'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cash', 'Cash'),
        ('Cheque', 'Cheque'),
    )
    method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='M-Pesa')

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    receipt_number = models.CharField(max_length=50, unique=True, null=True, blank=True, db_index=True)
    receipt_issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.CharField(max_length=100, blank=True, null=True, help_text="Name of the person/system that issued the receipt")
    covered_months = models.JSONField(default=list, blank=True)
    balance_after_payment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    mpesa_checkout_request_id = models.CharField(max_length=100, blank=True, null=True, unique=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.status == 'COMPLETED' and not self.receipt_number:
            raise ValidationError('Completed payments must have a receipt number.')
        if self.status == 'COMPLETED' and not self.receipt_issued_at:
            raise ValidationError('Completed payments must have a receipt issued date.')

    def save(self, *args, **kwargs):
        """
        Auto-populate receipt fields whenever a payment is saved as COMPLETED.

        Fixes the bug where a payment created directly as COMPLETED (e.g. via the
        landlord "New Payment" form) displayed empty Receipt No., Issued On,
        Issued By, and Covers Months on the receipt. This centralizes the receipt
        logic so it works across ALL creation paths.

        Fields explicitly set by the verify flows (verify_payment, payment_detail)
        are left untouched — only MISSING fields are filled in.
        """
        if self.status == 'COMPLETED':
            # 1) Issued by — the LANDLORD is the official issuer of the receipt.
            #    Never fall back to the tenant: receipts are issued by the owner,
            #    not by the person paying.
            if not self.issued_by:
                try:
                    landlord = self.lease.property.landlord if self.lease_id else None
                    self.issued_by = (landlord.full_name or landlord.business_name or 'System') if landlord else 'System'
                except Exception:
                    self.issued_by = 'System'

            # 2) Issued at — now if missing
            if not self.receipt_issued_at:
                self.receipt_issued_at = timezone.now()

            # 3) Covered months + balance — compute if missing
            if not self.covered_months and self.lease_id:
                try:
                    from .views import calculate_covered_months
                    mr = Decimal(self.lease.monthly_rent)
                    amt = Decimal(self.amount)
                    covered, remaining = calculate_covered_months(
                        self.lease.start_date, amt, mr, self.lease.end_date
                    )
                    if not self.covered_months:
                        self.covered_months = covered
                    if self.balance_after_payment is None:
                        self.balance_after_payment = remaining
                except Exception:
                    pass

            # 4) Receipt number — needs the DB id, set on first save
            if not self.receipt_number:
                # Save first to get the id, then set number + save again.
                # IMPORTANT: strip force_insert before the second save — otherwise
                # Django tries to INSERT again with the same PK → IntegrityError.
                force_insert = kwargs.pop('force_insert', False)
                if not self.pk:
                    super().save(*args, **kwargs)
                self.receipt_number = f"RCP-{self.pk}-{int(timezone.now().timestamp())}"
                if kwargs.get('update_fields'):
                    super().save(update_fields=['receipt_number'])
                else:
                    super().save(*args, **kwargs)
                return

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lease.tenant.full_name} - KSh {self.amount}"


# ------------------------------
# Maintenance Request Model — tenants report issues; landlords track resolution
# ------------------------------
class Maintenance(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='maintenance_requests')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='maintenance_requests')
    issue = models.TextField()
    description = models.TextField()
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Issue: {self.issue[:30]}..."


# ------------------------------
# System Notice Model — announcements targeted at all users, tenants, or landlords
# ------------------------------
class Notice(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    TARGET_CHOICES = (
        ('ALL', 'All Users'),
        ('ALL TENANTS', 'All Tenants'),
        ('ALL LANDLORDS', 'All Landlords'),
    )
    target = models.CharField(max_length=20, choices=TARGET_CHOICES)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

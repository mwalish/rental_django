from datetime import date

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

# ------------------------------
# Custom User Model
# ------------------------------
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'System Admin'),
        ('landlord', 'Landlord / Owner'),
        ('tenant', 'Tenant'),
    )

    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='tenant')
    phone_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(max_length=50, unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'phone_number']

    def __str__(self):
        return f"{self.username} ({self.role})"


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ------------------------------
# Landlord Profile
# ------------------------------
class Landlord(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='landlord_profile')
    full_name = models.CharField(max_length=150)
    id_number = models.CharField(max_length=15, unique=True)
    phone = models.CharField(max_length=15)
    mpesa_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField()
    business_name = models.CharField(max_length=200, blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/landlords/', blank=True, null=True)

    def __str__(self):
        return self.full_name

    @property
    def total_properties(self):
        return self.properties.count() if hasattr(self, 'properties') else 0

    @property
    def total_active_leases(self):
        if hasattr(self, 'properties'):
            return self.properties.filter(leases__is_active=True).distinct().count()
        return 0


# ------------------------------
# Tenant Profile
# ------------------------------
class Tenant(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tenant')
    profile_picture = models.ImageField(upload_to='profiles/tenants/', blank=True, null=True)
    full_name = models.CharField(max_length=150)
    id_number = models.CharField(max_length=15, unique=True)
    phone = models.CharField(max_length=15)
    alternative_phone = models.CharField(max_length=15, unique=True)
    email_address = models.EmailField(max_length=50, null=True)
    join_date = models.DateField(auto_now_add=True)
    exit_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.full_name


# ------------------------------
# Auto-create Profile Signal
# ------------------------------
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'landlord':
            Landlord.objects.create(
                user=instance,
                full_name=instance.get_full_name() or instance.username,
                phone=instance.phone_number
            )
        elif instance.role == 'tenant':
            Tenant.objects.create(
                user=instance,
                full_name=instance.get_full_name() or instance.username,
                phone=instance.phone_number,
                email_address=instance.email
            )
            


# ------------------------------
# 5. Property 
# ------------------------------
class Property(BaseModel):
    STATUS_CHOICES = [
    ("AVAILABLE", "Available"),
    ("OCCUPIED", "Occupied"),
    ("MAINTENANCE", "Under Maintenance"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")

    landlord = models.ForeignKey(Landlord, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=250)
    bedrooms = models.IntegerField(default=1)
    # Default rent set to 4000 KES
    rent_per_month = models.DecimalField(max_digits=10, decimal_places=2, default=4000.00)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, default=8500.00)  
    has_water = models.BooleanField(default=True)
    has_electricity = models.BooleanField(default=True)
    has_parking = models.BooleanField(blank=True,null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    image = models.ImageField(upload_to='properties/', blank=True, null=True)

    def __str__(self):
        return f"{self.title} - {self.location} | KES {self.rent_per_month}/month"


# -------------------------------------------------------------------
# 6. Rental Application for new tenant who would like to get a house
# -------------------------------------------------------------------
class RentalRequest(models.Model):
    REQUEST_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    tenant = models.ForeignKey(
        "Tenant",
        on_delete=models.CASCADE,
        related_name="rental_requests_made"
    )
    # ✅ Correct: uppercase "Property"
    property = models.ForeignKey(
        "Property",
        on_delete=models.CASCADE,
        related_name="rental_requests"
    )
    message = models.TextField(blank=True, null=True, help_text="Any message or request details")
    status = models.CharField(
        max_length=20,
        choices=REQUEST_STATUS_CHOICES,
        default="PENDING"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Prevent duplicate requests from same tenant for same property
        unique_together = ["tenant", "property"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tenant.full_name} → {self.property.title} ({self.status})"


# ------------------------------
# 7. Meeting / Property Viewing
# ------------------------------
class Meeting(BaseModel):
    STATUS_CHOICES = (
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='meetings')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='meetings')
    proposed_date = models.DateField()
    proposed_time = models.TimeField()
    purpose = models.CharField(max_length=100, default='View Property')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')

    def __str__(self):
        return f"Meeting: {self.property.title} | {self.proposed_date}"


# ------------------------------
# 8. Lease Agreement — AUTO SETS RENT FROM PROPERTY Auto-filled from property
# ------------------------------
class Lease(BaseModel):
    LEASE_STATUS_CHOICES = [
    ("ACTIVE", "Active"),
    ("EXPIRED", "Expired"),
    ("TERMINATED", "Terminated"),
    ]
    status = models.CharField(max_length=20, choices=LEASE_STATUS_CHOICES, default="ACTIVE")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='leases')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leases')
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=4000.00)
    deposit_paid = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.monthly_rent == 0:
            self.monthly_rent = self.property.rent_per_month
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Lease: {self.property.title} | KES {self.monthly_rent}"


# ------------------------------
# 9. Payment — AUTO SYNC AMOUNT 
# ------------------------------
from django.db import models
from datetime import date

class Payment(BaseModel):
    STATUS_CHOICES = (
        ('pending', 'Waiting Payment'),
        ('completed', 'Paid Successfully'),
        ('failed', 'Payment Failed'),
    )

    METHOD_CHOICES = (
        ('mpesa', 'M-Pesa'),
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
    )

    TYPE_CHOICES = (
        ('rent', 'Monthly Rent'),
        ('deposit', 'Security Deposit'),
        ('water', 'Water Bill'),
        ('electricity', 'Electricity Bill'),
        ('other', 'Other Charge'),
    )

    # ✅ Correct: use default only, no auto_now_add
    payment_date = models.DateField(default=date.today)

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='rent')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    for_month = models.CharField(max_length=20, blank=True, null=True)
    method = models.CharField(max_length=15, choices=METHOD_CHOICES)
    transaction_code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    phone_used = models.CharField(max_length=15, blank=True, null=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    receipt = models.FileField(upload_to='receipts/', blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.amount == 0:
            if self.payment_type == 'rent':
                self.amount = self.lease.monthly_rent
            elif self.payment_type == 'deposit':
                self.amount = self.lease.property.deposit
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.payment_type} - KES {self.amount} ({self.status})"


# ------------------------------
# 10. Maintenance Request
# ------------------------------
class Maintenance(BaseModel):
    STATUS_CHOICES = (
        ('open', 'Reported'),
        ('working', 'Maintainace underway'),
        ('done', 'Completed'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='maintenance')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='maintenance')
    issue = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    def __str__(self):
        return self.issue

# ------------------------------
# 11. NOTICE
# ------------------------------   

class Notice(BaseModel):
        TARGET_CHOICES=[('ALL','ALL TENANTS')]
        title=models.CharField(max_length=200)
        message=models.TextField()
        target=models.CharField(max_length=50,choices=TARGET_CHOICES)
        created_by=models.ForeignKey(User, on_delete=models.CASCADE)
        is_important=models.BooleanField(default=False)

        def __str__(self):
            return self.title
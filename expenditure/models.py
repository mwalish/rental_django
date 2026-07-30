from django.db import models


class Expenditure(models.Model):
    """Record of expenses/costs incurred by landlords or the system."""
    EXPENSE_CATEGORIES = (
        ('UTILITY', 'Utilities (Water, Electricity)'),
        ('MAINTENANCE', 'Maintenance & Repairs'),
        ('TAX', 'Taxes & Licenses'),
        ('SALARY', 'Staff Salaries'),
        ('MARKETING', 'Marketing & Advertising'),
        ('INSURANCE', 'Insurance'),
        ('OTHER', 'Other Expenses'),
    )

    title = models.CharField(max_length=200, help_text="Description of the expense")
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES, default='OTHER')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date_incurred = models.DateField(help_text="Date the expense was incurred")
    property = models.ForeignKey(
        'core.Property',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
        help_text="Property this expense relates to (optional)"
    )
    landlord = models.ForeignKey(
        'core.Landlord',
        on_delete=models.CASCADE,
        related_name='expenses',
        help_text="Landlord who incurred this expense"
    )
    receipt = models.FileField(upload_to='expenses/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_incurred']
        verbose_name = 'Expenditure'
        verbose_name_plural = 'Expenditures'

    def __str__(self):
        return f"{self.title} - KSh {self.amount}"


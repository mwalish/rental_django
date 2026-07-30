from django import forms
from core.models import Property, Maintenance, Notice


class PropertyForm(forms.ModelForm):
    """Form for creating/editing properties — only uses fields that exist on the Property model."""
    class Meta:
        model = Property
        fields = [
            'title', 'location', 'rent_per_month',
            'has_water', 'has_electricity', 'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'rent_per_month': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'has_water': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_electricity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class MaintenanceUpdateForm(forms.ModelForm):
    class Meta:
        model = Maintenance
        fields = ['status', 'description']


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'message', 'target']

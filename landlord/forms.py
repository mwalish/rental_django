from django import forms
from core.models import Property, Maintenance, Notice


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'title', 'location', 'bedrooms', 'rent_per_month', 'deposit',
            'has_water', 'has_electricity', 'has_parking', 'status', 'image'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'bedrooms': forms.NumberInput(attrs={'class': 'form-control'}),
            'rent_per_month': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'deposit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'has_water': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_electricity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_parking': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }


class MaintenanceUpdateForm(forms.ModelForm):
    class Meta:
        model = Maintenance
        fields = ['status', 'description']


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'message', 'target', 'is_important']
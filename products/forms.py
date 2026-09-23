from django import forms
from .models import Product, Category
from accounts.forms import StyledFormMixin


class ProductForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'category',
            'name',
            'weight',
            'price',
            'description',
            'image',
            'prep_time_hours',
            'is_customizable',
            'is_available',
        ]
        widgets = {
            'weight': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_weight', 'placeholder': 'e.g., 1 kg, 500g, 6 pcs, 1 piece'}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': '0.01', 'placeholder': 'Total price in ₹'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe your delicious bake, ingredients, flavor notes...'}),
            'prep_time_hours': forms.NumberInput(attrs={'min': 1, 'placeholder': 'Hours of notice needed'}),
            'is_customizable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'is_customizable' in self.fields:
            self.fields['is_customizable'].widget.attrs['class'] = 'form-check-input'
        if 'is_available' in self.fields:
            self.fields['is_available'].widget.attrs['class'] = 'form-check-input'
        self.fields['weight'].required = False
        self.fields['price'].required = True


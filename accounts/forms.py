from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User
from sellers.models import Seller


class StyledFormMixin:
    """Adds Bootstrap 'form-control' class to every field automatically."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()


class UserRegisterForm(StyledFormMixin, UserCreationForm):
    """Unified registration form for all new users (customers & future sellers)."""
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=True, label="Phone Number")
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=True, label="Delivery Address")

    class Meta:
        model = User
        fields = ['username', 'email', 'phone', 'address']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'customer'
        if commit:
            user.save()
        return user


# Backward-compatibility alias
CustomerRegisterForm = UserRegisterForm


class OTPVerificationForm(StyledFormMixin, forms.Form):
    """Form for entering email and phone verification OTPs."""
    email_otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        label="Email Verification Code",
        widget=forms.TextInput(attrs={'placeholder': 'Enter 6-digit Email OTP', 'autocomplete': 'one-time-code', 'maxlength': '6'})
    )
    phone_otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        label="Phone Verification Code",
        widget=forms.TextInput(attrs={'placeholder': 'Enter 6-digit Phone OTP', 'autocomplete': 'one-time-code', 'maxlength': '6'})
    )



class SellerOnboardingForm(StyledFormMixin, forms.Form):
    """In-app onboarding form for an authenticated user who wants to sell products."""
    business_name = forms.CharField(
        max_length=100,
        required=True,
        label="Business / Bakery Name",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Sweet Crust Bakery'})
    )
    fssai_number = forms.CharField(
        max_length=50,
        required=False,
        label="FSSAI License Number (optional)",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 11223344556677'})
    )
    phone = forms.CharField(
        max_length=15,
        required=True,
        label="Bakery Contact Number",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 9876543210'})
    )
    address = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Kitchen / Pickup address for orders'}),
        required=True,
        label="Kitchen / Pickup Address"
    )
    bank_account_number = forms.CharField(
        max_length=50,
        required=False,
        label="Bank Account Number (For Payouts)",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 123456789012'})
    )
    ifsc_code = forms.CharField(
        max_length=20,
        required=False,
        label="Bank IFSC Code (optional)",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. SBIN0001234'})
    )
    upi_id = forms.CharField(
        max_length=100,
        required=False,
        label="UPI ID (For Payouts)",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. bakeryname@okaxis'})
    )
    payment_qr = forms.ImageField(
        required=False,
        label="Payment QR Code Image"
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            if not self.initial.get('phone'):
                self.initial['phone'] = getattr(user, 'phone', '')
            if not self.initial.get('address'):
                self.initial['address'] = getattr(user, 'address', '')

    def save(self, user):
        """Creates or updates Seller profile and promotes user role to seller."""
        phone = self.cleaned_data['phone']
        address = self.cleaned_data['address']

        # Update user contact if modified
        user.phone = phone
        user.address = address
        user.role = 'seller'
        user.save()

        defaults = {
            'business_name': self.cleaned_data['business_name'],
            'fssai_number': self.cleaned_data.get('fssai_number', '').strip(),
            'bank_account_number': self.cleaned_data.get('bank_account_number', '').strip(),
            'ifsc_code': self.cleaned_data.get('ifsc_code', '').strip().upper(),
            'upi_id': self.cleaned_data.get('upi_id', '').strip(),
            'status': 'pending',
        }
        if self.cleaned_data.get('payment_qr'):
            defaults['payment_qr'] = self.cleaned_data['payment_qr']

        seller, created = Seller.objects.get_or_create(
            user=user,
            defaults=defaults
        )
        if not created:
            seller.business_name = self.cleaned_data['business_name']
            seller.fssai_number = self.cleaned_data.get('fssai_number', '').strip()
            seller.bank_account_number = self.cleaned_data.get('bank_account_number', '').strip()
            seller.ifsc_code = self.cleaned_data.get('ifsc_code', '').strip().upper()
            seller.upi_id = self.cleaned_data.get('upi_id', '').strip()
            if self.cleaned_data.get('payment_qr'):
                seller.payment_qr = self.cleaned_data['payment_qr']
            seller.status = 'pending'
            seller.save()

        return seller


class StyledAuthenticationForm(StyledFormMixin, AuthenticationForm):
    pass
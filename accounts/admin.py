from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPVerification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'phone', 'is_email_verified', 'is_phone_verified', 'is_staff', 'is_active')
    list_filter = ('role', 'is_email_verified', 'is_phone_verified', 'is_staff', 'is_superuser', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Bakery Profile', {'fields': ('role', 'phone', 'address', 'wallet_balance', 'is_email_verified', 'is_phone_verified')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Bakery Profile', {'fields': ('role', 'phone', 'address', 'is_email_verified', 'is_phone_verified')}),
    )


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'phone', 'email_otp', 'phone_otp', 'is_used', 'expires_at', 'created_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('email', 'phone', 'email_otp', 'phone_otp')


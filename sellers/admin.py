from django.contrib import admin
from .models import Seller


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'fssai_number', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('business_name', 'user__username', 'fssai_number', 'user__email')
    actions = ['approve_sellers', 'reject_sellers']

    @admin.action(description="Approve selected sellers")
    def approve_sellers(self, request, queryset):
        count = queryset.update(status='approved')
        self.message_user(request, f"{count} seller(s) approved.")

    @admin.action(description="Reject selected sellers")
    def reject_sellers(self, request, queryset):
        count = queryset.update(status='rejected')
        self.message_user(request, f"{count} seller(s) rejected.")
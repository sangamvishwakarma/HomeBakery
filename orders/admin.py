from django.contrib import admin
from .models import CartItem, Order, OrderItem, Review, Payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price_at_order', 'customization_notes', 'subtotal')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'seller', 'total_amount', 'status', 'payment_method', 'payment_status', 'transaction_id', 'delivery_date', 'order_date')
    list_filter = ('status', 'payment_method', 'payment_status', 'order_date')
    search_fields = ('id', 'customer__username', 'seller__business_name', 'delivery_address', 'contact_number', 'transaction_id')
    inlines = [OrderItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'amount', 'gateway', 'payment_method', 'status', 'razorpay_payment_id', 'created_at')
    list_filter = ('gateway', 'status', 'payment_method', 'created_at')
    search_fields = ('customer__username', 'razorpay_order_id', 'razorpay_payment_id')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'customer__username', 'comment')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity', 'delivery_date', 'added_at')
    search_fields = ('customer__username', 'product__name')

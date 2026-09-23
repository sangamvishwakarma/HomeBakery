from django.db import models
from accounts.models import User
from sellers.models import Seller
from products.models import Product


class CartItem(models.Model):
    UNIT_CHOICES = [
        ('piece', 'Piece(s)'),
        ('kg', 'Kg(s)'),
    ]
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=6, decimal_places=2, default=1.0)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='piece')
    customization_notes = models.TextField(blank=True)
    delivery_date = models.DateTimeField()
    added_at = models.DateTimeField(auto_now_add=True)

    @property
    def unit_price(self):
        return self.product.get_price_for_unit(self.unit)

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def display_name(self):
        return self.product.display_name

    @property
    def formatted_quantity(self):
        qty_val = int(self.quantity) if self.quantity == int(self.quantity) else self.quantity
        return str(qty_val)

    def __str__(self):
        return f"{self.customer.username} - {self.display_name} (Qty: {self.formatted_quantity})"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('upi', 'UPI'),
        ('card', 'Credit/Debit Card'),
        ('netbanking', 'Net Banking'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='orders')
    delivery_address = models.TextField()
    contact_number = models.CharField(max_length=15)
    payment_method = models.CharField(max_length=15, choices=PAYMENT_CHOICES, default='cod')
    payment_status = models.CharField(max_length=15, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    order_date = models.DateTimeField(auto_now_add=True)
    delivery_date = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def invoice_number(self):
        return f"INV-{self.id:05d}"

    def __str__(self):
        return f"Order #{self.id} - {self.customer.username}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
    ]
    GATEWAY_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('cod', 'Cash on Delivery'),
    ]

    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='razorpay')
    payment_method = models.CharField(max_length=20, default='upi')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.id} - {self.customer.username} - ₹{self.amount} ({self.status})"


class OrderItem(models.Model):
    UNIT_CHOICES = [
        ('piece', 'Piece(s)'),
        ('kg', 'Kg(s)'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=6, decimal_places=2, default=1.0)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='piece')
    price_at_order = models.DecimalField(max_digits=8, decimal_places=2)
    weight_at_order = models.CharField(max_length=50, blank=True, default='')
    customization_notes = models.TextField(blank=True)

    @property
    def effective_weight(self):
        return self.weight_at_order or (self.product.weight if self.product else '')

    @property
    def display_name(self):
        weight = self.effective_weight
        if weight:
            return f"{self.product.name} ({weight})"
        return self.product.name

    @property
    def subtotal(self):
        return self.price_at_order * self.quantity

    @property
    def formatted_quantity(self):
        qty_val = int(self.quantity) if self.quantity == int(self.quantity) else self.quantity
        return str(qty_val)


class Review(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rating}★ - {self.product.name}"
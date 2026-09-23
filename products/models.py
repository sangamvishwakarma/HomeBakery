from django.db import models
from sellers.models import Seller


class Category(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    weight = models.CharField(max_length=50, blank=True, default='', help_text="Weight or piece description (e.g. 1 kg, 500g, 6 pcs, 1 piece)")
    price = models.DecimalField(max_digits=8, decimal_places=2, help_text="Total price for this item")
    unit = models.CharField(max_length=10, default='piece', blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_customizable = models.BooleanField(default=False)
    prep_time_hours = models.IntegerField(default=24)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_name(self):
        if self.weight:
            return f"{self.name} ({self.weight})"
        return self.name

    def get_price_for_unit(self, unit_type='piece'):
        return self.price

    @property
    def price_display(self):
        return f"₹{self.price}"

    def __str__(self):
        return self.display_name
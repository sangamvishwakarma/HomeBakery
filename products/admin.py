from django.contrib import admin
from .models import Category, Product

admin.site.register(Category)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)
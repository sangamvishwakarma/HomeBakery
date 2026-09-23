from django.core.management.base import BaseCommand
from products.models import Category


class Command(BaseCommand):
    help = "Seed initial bakery categories if none exist"

    def handle(self, *args, **kwargs):
        default_categories = [
            "Cakes",
            "Pastries & Cupcakes",
            "Breads & Buns",
            "Cookies & Biscuits",
            "Pies & Tarts",
            "Savory Bakes",
        ]
        created_count = 0
        for name in default_categories:
            cat, created = Category.objects.get_or_create(name=name)
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully processed categories. {created_count} new categories created."))


from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from sellers.models import Seller
from products.models import Category, Product
from orders.models import Order, Review
from django.utils import timezone


class SellersTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.customer = User.objects.create_user(username='customer1', password='Password123!', role='customer')

        self.approved_user = User.objects.create_user(username='approved_baker', password='Password123!', role='seller')
        self.approved_seller = Seller.objects.create(
            user=self.approved_user,
            business_name="Crust & Crumb",
            status='approved'
        )

        self.pending_user = User.objects.create_user(username='pending_baker', password='Password123!', role='seller')
        self.pending_seller = Seller.objects.create(
            user=self.pending_user,
            business_name="Wait Bakery",
            status='pending'
        )

        self.rejected_user = User.objects.create_user(username='rejected_baker', password='Password123!', role='seller')
        self.rejected_seller = Seller.objects.create(
            user=self.rejected_user,
            business_name="No Bakery",
            status='rejected'
        )

    def test_non_seller_redirected_from_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('seller_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('seller_register'))

    def test_pending_seller_dashboard(self):
        self.client.force_login(self.pending_user)
        response = self.client.get(reverse('seller_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your seller account is awaiting administrator approval")

    def test_rejected_seller_dashboard(self):
        self.client.force_login(self.rejected_user)
        response = self.client.get(reverse('seller_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application Rejected")

    def test_approved_seller_dashboard_metrics(self):
        self.client.force_login(self.approved_user)

        cat = Category.objects.create(name="Breads")
        p1 = Product.objects.create(
            seller=self.approved_seller,
            category=cat,
            name="Sourdough Loaf",
            price=200.00,
            prep_time_hours=12,
        )

        # Reviews for average rating
        Review.objects.create(customer=self.customer, product=p1, rating=5, comment="Amazing!")
        Review.objects.create(customer=self.customer, product=p1, rating=4, comment="Very good crust")

        # Orders: 1 pending, 1 delivered
        now = timezone.now()
        Order.objects.create(
            customer=self.customer,
            seller=self.approved_seller,
            delivery_address="123 Street",
            contact_number="9999999999",
            delivery_date=now,
            total_amount=230.00,
            status='pending'
        )
        Order.objects.create(
            customer=self.customer,
            seller=self.approved_seller,
            delivery_address="123 Street",
            contact_number="9999999999",
            delivery_date=now,
            total_amount=430.00,
            status='delivered'
        )

        response = self.client.get(reverse('seller_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_products'], 1)
        self.assertEqual(response.context['pending_orders'], 1)
        self.assertEqual(response.context['total_earnings'], 430.00)
        self.assertEqual(response.context['avg_rating'], 4.5)
        self.assertContains(response, "4.5")

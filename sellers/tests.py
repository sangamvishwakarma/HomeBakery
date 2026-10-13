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
        self.assertEqual(float(response.context['gross_sales']), 430.00)
        self.assertEqual(float(response.context['total_commission']), 21.50)
        self.assertEqual(float(response.context['total_earnings']), 408.50)
        self.assertEqual(response.context['avg_rating'], 4.5)
        self.assertContains(response, "408.50")
        self.assertContains(response, "21.50")
        self.assertContains(response, "4.5")

    def test_seller_update_payment_details(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.approved_user)
        self.assertFalse(self.approved_seller.has_payment_details)

        # Tiny valid 1x1 GIF for QR upload test
        gif_bytes = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
            b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00'
            b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
            b'\x44\x01\x00\x3b'
        )
        qr_file = SimpleUploadedFile('upi_qr.gif', gif_bytes, content_type='image/gif')

        res = self.client.post(reverse('update_seller_payment'), {
            'bank_account_number': '987654321012',
            'ifsc_code': 'sbin0001234',
            'upi_id': 'crustandcrumb@okaxis',
            'payment_qr': qr_file,
        })
        self.assertRedirects(res, reverse('seller_dashboard'))

        self.approved_seller.refresh_from_db()
        self.assertTrue(self.approved_seller.has_payment_details)
        self.assertEqual(self.approved_seller.bank_account_number, '987654321012')
        self.assertEqual(self.approved_seller.ifsc_code, 'SBIN0001234')
        self.assertEqual(self.approved_seller.upi_id, 'crustandcrumb@okaxis')
        self.assertTrue(bool(self.approved_seller.payment_qr))

        dash = self.client.get(reverse('seller_dashboard'))
        self.assertContains(dash, '987654321012')
        self.assertContains(dash, 'crustandcrumb@okaxis')
        self.assertContains(dash, 'Payout Details Configured')


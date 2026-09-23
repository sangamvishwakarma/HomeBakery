from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from sellers.models import Seller


class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_unified_registration_view_renders(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')

    def test_unified_registration_success(self):
        response = self.client.post(reverse('register'), {
            'username': 'alice',
            'email': 'alice@example.com',
            'phone': '9876543210',
            'address': '12 Baker Street, London',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_list'))

        user = User.objects.get(username='alice')
        self.assertEqual(user.role, 'customer')
        self.assertEqual(user.phone, '9876543210')
        self.assertEqual(user.address, '12 Baker Street, London')

    def test_registration_password_mismatch(self):
        response = self.client.post(reverse('register'), {
            'username': 'bob',
            'email': 'bob@example.com',
            'phone': '9876543210',
            'address': '12 Baker Street',
            'password1': 'ComplexPass123!',
            'password2': 'WrongPass456!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='bob').exists())

    def test_seller_onboarding_requires_login(self):
        response = self.client.get(reverse('seller_register'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    def test_in_app_seller_onboarding_success(self):
        # Register a standard customer user first
        user = User.objects.create_user(
            username='baker_bob',
            email='bob@bakery.com',
            phone='9123456780',
            address='55 Pastry Lane',
            password='BakePassword123!',
            role='customer'
        )
        self.client.force_login(user)

        # GET the in-app seller onboarding page
        get_res = self.client.get(reverse('seller_register'))
        self.assertEqual(get_res.status_code, 200)
        self.assertTemplateUsed(get_res, 'accounts/seller_register.html')
        self.assertContains(get_res, 'baker_bob')

        # POST seller application
        post_res = self.client.post(reverse('seller_register'), {
            'business_name': "Bob's Artisanal Bakes",
            'fssai_number': 'FSSAI123456789',
            'phone': '9123456780',
            'address': '55 Pastry Lane, Suite 2',
        })
        self.assertEqual(post_res.status_code, 302)
        self.assertRedirects(post_res, reverse('seller_dashboard'))

        # Check user role promoted to seller
        user.refresh_from_db()
        self.assertEqual(user.role, 'seller')
        self.assertEqual(user.address, '55 Pastry Lane, Suite 2')

        # Check Seller model created
        seller = Seller.objects.get(user=user)
        self.assertEqual(seller.business_name, "Bob's Artisanal Bakes")
        self.assertEqual(seller.fssai_number, 'FSSAI123456789')
        self.assertEqual(seller.status, 'pending')

    def test_already_approved_seller_accessing_seller_register(self):
        seller_user = User.objects.create_user(
            username='existing_baker',
            password='Password123!',
            role='seller'
        )
        Seller.objects.create(
            user=seller_user,
            business_name="Existing Kitchen",
            status='approved'
        )
        self.client.force_login(seller_user)
        response = self.client.get(reverse('seller_register'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('seller_dashboard'))

    def test_login_and_logout(self):
        user = User.objects.create_user(
            username='charlie',
            password='TestPassword123!',
            role='customer'
        )
        login_response = self.client.post(reverse('login'), {
            'username': 'charlie',
            'password': 'TestPassword123!',
        })
        self.assertEqual(login_response.status_code, 302)

        logout_response = self.client.get(reverse('logout'))
        self.assertEqual(logout_response.status_code, 302)
        self.assertRedirects(logout_response, reverse('product_list'))

    def test_admin_dashboard_access(self):
        admin_user = User.objects.create_superuser(
            username='admin_boss',
            password='AdminPass123!',
            email='admin@bakery.com'
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/admin_dashboard.html')
        self.assertContains(response, "Platform Admin Portal")

    def test_admin_dashboard_forbidden_for_customer(self):
        customer = User.objects.create_user(
            username='regular_customer',
            password='Password123!',
            role='customer'
        )
        self.client.force_login(customer)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_list'))

    def test_admin_approve_and_reject_seller(self):
        admin_user = User.objects.create_superuser(
            username='superadmin',
            password='AdminPass123!',
            email='super@bakery.com'
        )
        seller_user = User.objects.create_user(username='baker_dave', password='Password123!', role='seller')
        seller = Seller.objects.create(user=seller_user, business_name="Dave's Cakes", status='pending')

        self.client.force_login(admin_user)

        # Approve seller
        app_res = self.client.post(reverse('admin_approve_seller', args=[seller.id]))
        self.assertEqual(app_res.status_code, 302)
        seller.refresh_from_db()
        self.assertEqual(seller.status, 'approved')

        # Reject seller
        rej_res = self.client.post(reverse('admin_reject_seller', args=[seller.id]))
        self.assertEqual(rej_res.status_code, 302)
        seller.refresh_from_db()
        self.assertEqual(seller.status, 'rejected')

    def test_admin_toggle_user_status(self):
        admin_user = User.objects.create_superuser(username='super2', password='AdminPass123!')
        target_user = User.objects.create_user(username='spammer', password='Password123!')

        self.client.force_login(admin_user)
        self.assertTrue(target_user.is_active)

        # Deactivate
        self.client.post(reverse('admin_toggle_user_status', args=[target_user.id]))
        target_user.refresh_from_db()
        self.assertFalse(target_user.is_active)

        # Reactivate
        self.client.post(reverse('admin_toggle_user_status', args=[target_user.id]))
        target_user.refresh_from_db()
        self.assertTrue(target_user.is_active)

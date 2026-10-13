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

    def test_unified_registration_redirects_to_otp_and_verifies_successfully(self):
        from accounts.models import OTPVerification

        response = self.client.post(reverse('register'), {
            'username': 'alice',
            'email': 'alice@example.com',
            'phone': '9876543210',
            'address': '12 Baker Street, London',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_otp'))

        # User is not created yet before OTP verification
        self.assertFalse(User.objects.filter(username='alice').exists())

        # An OTPVerification record was created
        otp = OTPVerification.objects.get(email='alice@example.com')
        self.assertFalse(otp.is_used)
        self.assertEqual(len(otp.email_otp), 6)
        self.assertEqual(len(otp.phone_otp), 6)

        # GET the verify-otp page renders
        get_res = self.client.get(reverse('verify_otp'))
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, 'Verify Your Identity')

        # Test POST wrong OTPs -> fails
        bad_post = self.client.post(reverse('verify_otp'), {
            'email_otp': '000000',
            'phone_otp': '111111',
        })
        self.assertEqual(bad_post.status_code, 200)
        self.assertFalse(User.objects.filter(username='alice').exists())

        # Test POST correct OTPs -> succeeds
        good_post = self.client.post(reverse('verify_otp'), {
            'email_otp': otp.email_otp,
            'phone_otp': otp.phone_otp,
        })
        self.assertEqual(good_post.status_code, 302)
        self.assertRedirects(good_post, reverse('product_list'))

        # User is now created and verified
        user = User.objects.get(username='alice')
        self.assertEqual(user.role, 'customer')
        self.assertEqual(user.phone, '9876543210')
        self.assertEqual(user.address, '12 Baker Street, London')
        self.assertTrue(user.is_email_verified)
        self.assertTrue(user.is_phone_verified)

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_resend_otp_and_cancel_registration(self):
        from accounts.models import OTPVerification

        # Step 1: initiate registration
        self.client.post(reverse('register'), {
            'username': 'charlie_test',
            'email': 'charlie@example.com',
            'phone': '9876543299',
            'address': '221B Baker St',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        first_otp = OTPVerification.objects.get(email='charlie@example.com')

        # Step 2: request resend
        resend_res = self.client.get(reverse('resend_otp'))
        self.assertEqual(resend_res.status_code, 302)
        self.assertRedirects(resend_res, reverse('verify_otp'))

        # A new OTP record exists
        new_otp = OTPVerification.objects.filter(email='charlie@example.com').latest('id')
        self.assertNotEqual(new_otp.id, first_otp.id)

        # Step 3: cancel registration clears pending session
        cancel_res = self.client.get(reverse('cancel_registration'))
        self.assertEqual(cancel_res.status_code, 302)
        self.assertRedirects(cancel_res, reverse('register'))

        # verify_otp now redirects to register because session is cleared
        no_session_res = self.client.get(reverse('verify_otp'))
        self.assertEqual(no_session_res.status_code, 302)
        self.assertRedirects(no_session_res, reverse('register'))

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

    def test_admin_dashboard_commission_and_payout_metrics(self):
        from orders.models import Order
        from django.utils import timezone

        admin_user = User.objects.create_superuser(username='admin_comm', password='AdminPass123!')
        customer = User.objects.create_user(username='cust_comm', password='Password123!', role='customer')
        seller_user = User.objects.create_user(username='baker_comm', password='Password123!', role='seller')
        seller = Seller.objects.create(user=seller_user, business_name="Golden Crust", status='approved')

        Order.objects.create(
            customer=customer,
            seller=seller,
            delivery_address="100 Main St",
            contact_number="9876543210",
            delivery_date=timezone.now(),
            total_amount=1000.00,
            status='delivered'
        )

        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.context['total_revenue']), 1000.00)
        self.assertEqual(float(response.context['total_admin_commission']), 50.00)
        self.assertEqual(float(response.context['total_seller_payout']), 950.00)
        self.assertContains(response, "50.00")
        self.assertContains(response, "950.00")

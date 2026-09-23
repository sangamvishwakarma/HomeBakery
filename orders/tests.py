import datetime
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from sellers.models import Seller
from products.models import Category, Product
from orders.models import CartItem, Order, OrderItem, Review, Payment
from orders.views import generate_sandbox_signature


class OrdersTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Customer
        self.customer = User.objects.create_user(
            username='cust_jane',
            password='Password123!',
            role='customer',
            phone='9876543210',
            address='742 Evergreen Terrace'
        )

        # Sellers
        self.seller_user1 = User.objects.create_user(username='baker1', password='Password123!', role='seller')
        self.seller1 = Seller.objects.create(user=self.seller_user1, business_name="Baker One", status='approved')

        self.seller_user2 = User.objects.create_user(username='baker2', password='Password123!', role='seller')
        self.seller2 = Seller.objects.create(user=self.seller_user2, business_name="Baker Two", status='approved')

        # Categories & Products
        self.category = Category.objects.create(name="Pastries")
        self.product1 = Product.objects.create(
            seller=self.seller1,
            category=self.category,
            name="Croissant",
            price=80.00,
            prep_time_hours=4,
            is_available=True,
            is_customizable=True,
        )
        self.product2 = Product.objects.create(
            seller=self.seller2,
            category=self.category,
            name="Danish Pastry",
            price=120.00,
            prep_time_hours=6,
            is_available=True,
        )

    def test_add_to_cart_valid(self):
        self.client.force_login(self.customer)
        valid_delivery = (timezone.now() + datetime.timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M')

        response = self.client.post(reverse('add_to_cart', args=[self.product1.id]), {
            'quantity': 2,
            'delivery_date': valid_delivery,
            'customization_notes': 'Extra butter please',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cart_view'))

        cart_item = CartItem.objects.get(customer=self.customer, product=self.product1)
        self.assertEqual(cart_item.quantity, 2)
        self.assertEqual(cart_item.customization_notes, 'Extra butter please')

    def test_add_to_cart_insufficient_prep_time(self):
        self.client.force_login(self.customer)
        # product1 requires 4 hours prep time, but we request 1 hour from now
        too_soon_delivery = (timezone.now() + datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')

        response = self.client.post(reverse('add_to_cart', args=[self.product1.id]), {
            'quantity': 1,
            'delivery_date': too_soon_delivery,
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_detail', args=[self.product1.id]))
        self.assertFalse(CartItem.objects.filter(customer=self.customer).exists())

    def test_add_to_cart_missing_delivery_date(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('add_to_cart', args=[self.product1.id]), {
            'quantity': 1,
            'delivery_date': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_detail', args=[self.product1.id]))
        self.assertFalse(CartItem.objects.filter(customer=self.customer).exists())

    def test_cart_view_and_quantity_update(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)
        item = CartItem.objects.create(
            customer=self.customer,
            product=self.product1,
            quantity=2,
            delivery_date=deliv
        )

        response = self.client.get(reverse('cart_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Croissant")
        self.assertContains(response, "₹160.00")  # 2 * 80

        # Increase quantity
        self.client.post(reverse('update_cart_quantity', args=[item.id]), {'action': 'increase'})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

        # Decrease quantity
        self.client.post(reverse('update_cart_quantity', args=[item.id]), {'action': 'decrease'})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        # Remove from cart
        rem_res = self.client.post(reverse('remove_from_cart', args=[item.id]))
        self.assertEqual(rem_res.status_code, 302)
        self.assertFalse(CartItem.objects.filter(id=item.id).exists())

    def test_checkout_multi_seller_atomic_orders(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)

        # Items from 2 different sellers
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=2, delivery_date=deliv)
        CartItem.objects.create(customer=self.customer, product=self.product2, quantity=1, delivery_date=deliv)

        # GET checkout page
        get_res = self.client.get(reverse('checkout'))
        self.assertEqual(get_res.status_code, 200)
        # subtotal: 160 + 120 = 280, 2 sellers * 30 = 60 delivery fee, grand_total = 340
        self.assertEqual(get_res.context['cart_total'], 280.00)
        self.assertEqual(get_res.context['delivery_fee'], 60)
        self.assertEqual(get_res.context['grand_total'], 340.00)

        # POST checkout
        post_res = self.client.post(reverse('checkout'), {
            'delivery_address': 'Flat 4B, Sunflower Apts',
            'contact_number': '9876543210',
            'payment_method': 'cod',
        })
        self.assertEqual(post_res.status_code, 302)
        self.assertRedirects(post_res, reverse('customer_orders'))

        # Cart should now be empty
        self.assertEqual(CartItem.objects.filter(customer=self.customer).count(), 0)

        # 2 orders created, one for each seller
        orders = Order.objects.filter(customer=self.customer)
        self.assertEqual(orders.count(), 2)

        order1 = orders.get(seller=self.seller1)
        self.assertEqual(order1.total_amount, 160.00 + 30)  # 190.00
        self.assertEqual(order1.items.count(), 1)
        self.assertEqual(order1.items.first().product, self.product1)

        order2 = orders.get(seller=self.seller2)
        self.assertEqual(order2.total_amount, 120.00 + 30)  # 150.00
        self.assertEqual(order2.items.count(), 1)
        self.assertEqual(order2.items.first().product, self.product2)

    def test_customer_orders_view(self):
        self.client.force_login(self.customer)
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='Test Address',
            contact_number='9999999999',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
            status='preparing'
        )
        OrderItem.objects.create(order=order, product=self.product1, quantity=2, price_at_order=80.00)

        response = self.client.get(reverse('customer_orders'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Order #{order.id}")
        self.assertContains(response, "Baker One")
        self.assertContains(response, "Preparing")

    def test_order_detail_view_permissions(self):
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='Test Address',
            contact_number='9999999999',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
        )

        # Customer who ordered can view
        self.client.force_login(self.customer)
        res_cust = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(res_cust.status_code, 200)

        # Seller fulfilling order can view
        self.client.force_login(self.seller_user1)
        res_seller = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(res_seller.status_code, 200)

        # Another unrelated customer cannot view
        other_user = User.objects.create_user(username='intruder', password='Password123!', role='customer')
        self.client.force_login(other_user)
        res_unauth = self.client.get(reverse('order_detail', args=[order.id]))
        self.assertEqual(res_unauth.status_code, 302)

    def test_update_order_status_by_seller(self):
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='Test Address',
            contact_number='9999999999',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
            status='pending'
        )
        self.client.force_login(self.seller_user1)
        res = self.client.post(reverse('update_order_status', args=[order.id]), {'status': 'ready'})
        self.assertEqual(res.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, 'ready')

    def test_add_review(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('add_review', args=[self.product1.id]), {
            'rating': 5,
            'comment': 'Flaky, buttery, best croissant in the city!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('product_detail', args=[self.product1.id]))

        review = Review.objects.get(customer=self.customer, product=self.product1)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Flaky, buttery, best croissant in the city!')

    def test_checkout_cod_sets_payment_status_pending(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=1, delivery_date=deliv)

        response = self.client.post(reverse('checkout'), {
            'delivery_address': '123 Baker Street',
            'contact_number': '9876543210',
            'payment_method': 'cod',
        })
        self.assertEqual(response.status_code, 302)
        order = Order.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.payment_status, 'pending')
        self.assertEqual(order.payment_method, 'cod')
        self.assertTrue(order.transaction_id.startswith('COD-'))

        # Check Payment record created
        payment = Payment.objects.filter(customer=self.customer, gateway='cod').first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, 'successful')

    def test_create_payment_order_api(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=2, delivery_date=deliv)

        response = self.client.post(
            reverse('create_payment_order'),
            data=json.dumps({
                'delivery_address': '456 Gourmet Lane',
                'contact_number': '9876543210',
                'payment_method': 'upi',
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['razorpay_order_id'].startswith('order_test_'))
        self.assertEqual(data['amount'], 190.0)  # 2 * 80 + 30
        self.assertEqual(data['amount_in_paise'], 19000)
        self.assertIn('simulated_payment_id', data)
        self.assertIn('simulated_signature', data)

        payment = Payment.objects.get(id=data['payment_id'])
        self.assertEqual(payment.status, 'initiated')
        self.assertEqual(payment.payment_method, 'upi')

    def test_verify_payment_success_creates_order(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=1, delivery_date=deliv)

        order_id = f"order_test_{int(timezone.now().timestamp())}_{self.customer.id}"
        payment_id = f"pay_test_{int(timezone.now().timestamp())}_99"
        valid_signature = generate_sandbox_signature(order_id, payment_id)

        # Pre-create initiated Payment record
        payment = Payment.objects.create(
            customer=self.customer,
            amount=110.0,
            gateway='razorpay',
            payment_method='card',
            razorpay_order_id=order_id,
            status='initiated'
        )

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_signature,
                'delivery_address': '789 Patisserie Road',
                'contact_number': '9123456789',
                'payment_method': 'card',
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')

        # Order created
        order = Order.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.payment_method, 'card')
        self.assertEqual(order.transaction_id, payment_id)
        self.assertIsNotNone(order.paid_at)

        # Payment updated
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'successful')
        self.assertEqual(payment.razorpay_payment_id, payment_id)

        # Cart cleared
        self.assertFalse(CartItem.objects.filter(customer=self.customer).exists())

    def test_verify_payment_tampered_signature_rejected(self):
        self.client.force_login(self.customer)
        deliv = timezone.now() + datetime.timedelta(hours=12)
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=1, delivery_date=deliv)

        order_id = f"order_test_{int(timezone.now().timestamp())}_{self.customer.id}"
        payment_id = f"pay_test_{int(timezone.now().timestamp())}_88"
        fake_signature = "bad_tampered_signature_12345"

        Payment.objects.create(
            customer=self.customer,
            amount=110.0,
            gateway='razorpay',
            payment_method='upi',
            razorpay_order_id=order_id,
            status='initiated'
        )

        response = self.client.post(
            reverse('verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': fake_signature,
                'delivery_address': '789 Patisserie Road',
                'contact_number': '9123456789',
                'payment_method': 'upi',
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 'error')

        # Cart must NOT be deleted on payment failure
        self.assertTrue(CartItem.objects.filter(customer=self.customer).exists())
        # No order created
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())

    def test_order_invoice_customer_view(self):
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='742 Evergreen Terrace',
            contact_number='9876543210',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
            payment_method='upi',
            payment_status='paid',
            transaction_id='pay_test_inv_123',
            paid_at=timezone.now(),
        )
        OrderItem.objects.create(order=order, product=self.product1, quantity=2, price_at_order=80.00)

        self.client.force_login(self.customer)
        response = self.client.get(reverse('order_invoice', args=[order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tax Invoice / Bill")
        self.assertContains(response, order.invoice_number)
        self.assertContains(response, "Baker One")
        self.assertContains(response, "cust_jane")
        self.assertContains(response, "Croissant")
        self.assertContains(response, "₹160.0")
        self.assertContains(response, "₹190.0")
        self.assertContains(response, "Paid Online")
        self.assertContains(response, "pay_test_inv_123")
        self.assertContains(response, "window.print()")

    def test_order_invoice_seller_view(self):
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='742 Evergreen Terrace',
            contact_number='9876543210',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
            payment_method='cod',
            payment_status='pending',
            transaction_id='COD-12345',
        )
        OrderItem.objects.create(order=order, product=self.product1, quantity=2, price_at_order=80.00)

        self.client.force_login(self.seller_user1)
        response = self.client.get(reverse('order_invoice', args=[order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash on Delivery")
        self.assertContains(response, order.invoice_number)
        self.assertContains(response, "Back to Seller Dashboard")

    def test_order_invoice_unauthorized_user_redirected(self):
        order = Order.objects.create(
            customer=self.customer,
            seller=self.seller1,
            delivery_address='742 Evergreen Terrace',
            contact_number='9876543210',
            delivery_date=timezone.now() + datetime.timedelta(hours=24),
            total_amount=190.00,
        )
        unrelated_user = User.objects.create_user(username='stranger', password='Password123!', role='customer')
        self.client.force_login(unrelated_user)
        response = self.client.get(reverse('order_invoice', args=[order.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('customer_orders'))

    def test_add_to_cart_with_weight(self):
        cake = Product.objects.create(
            seller=self.seller1,
            category=self.category,
            name="Vanilla Dream Cake",
            weight='1 kg',
            price=500.00,
            prep_time_hours=4,
            is_available=True,
        )
        self.client.force_login(self.customer)
        valid_delivery = (timezone.now() + datetime.timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M')

        response = self.client.post(reverse('add_to_cart', args=[cake.id]), {
            'quantity': 2,
            'delivery_date': valid_delivery,
        })
        self.assertEqual(response.status_code, 302)

        item = CartItem.objects.get(customer=self.customer, product=cake)
        self.assertEqual(float(item.quantity), 2.0)
        self.assertEqual(item.display_name, 'Vanilla Dream Cake (1 kg)')
        self.assertEqual(float(item.subtotal), 1000.00)  # 2 * 500

    def test_update_cart_quantity(self):
        cake = Product.objects.create(
            seller=self.seller1,
            category=self.category,
            name="Vanilla Dream Cake",
            weight='1 kg',
            price=500.00,
            prep_time_hours=4,
            is_available=True,
        )
        deliv = timezone.now() + datetime.timedelta(hours=10)
        item = CartItem.objects.create(
            customer=self.customer,
            product=cake,
            quantity=1.0,
            delivery_date=deliv
        )
        self.client.force_login(self.customer)

        # Increase by 1
        self.client.post(reverse('update_cart_quantity', args=[item.id]), {'action': 'increase'})
        item.refresh_from_db()
        self.assertEqual(float(item.quantity), 2.0)

        # Decrease by 1
        self.client.post(reverse('update_cart_quantity', args=[item.id]), {'action': 'decrease'})
        item.refresh_from_db()
        self.assertEqual(float(item.quantity), 1.0)

    def test_checkout_with_weighted_products(self):
        cake = Product.objects.create(
            seller=self.seller1,
            category=self.category,
            name="Vanilla Dream Cake",
            weight='1 kg',
            price=500.00,
            prep_time_hours=4,
            is_available=True,
        )
        self.product1.weight = '1 pc'
        self.product1.save()

        deliv = timezone.now() + datetime.timedelta(hours=10)
        # 2 pieces of croissant (80 * 2 = 160)
        CartItem.objects.create(customer=self.customer, product=self.product1, quantity=2, delivery_date=deliv)
        # 1 cake (500 * 1 = 500)
        CartItem.objects.create(customer=self.customer, product=cake, quantity=1, delivery_date=deliv)

        self.client.force_login(self.customer)
        # Total items: 160 + 500 = 660 + 30 delivery = 690
        post_res = self.client.post(reverse('checkout'), {
            'delivery_address': 'Flat 101, Baker Heights',
            'contact_number': '9876543210',
            'payment_method': 'cod',
        })
        self.assertEqual(post_res.status_code, 302)

        order = Order.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(order)
        self.assertEqual(float(order.total_amount), 690.00)
        self.assertEqual(order.items.count(), 2)

        piece_item = order.items.get(product=self.product1)
        self.assertEqual(piece_item.display_name, 'Croissant (1 pc)')
        self.assertEqual(float(piece_item.quantity), 2.0)

        kg_item = order.items.get(product=cake)
        self.assertEqual(kg_item.display_name, 'Vanilla Dream Cake (1 kg)')
        self.assertEqual(float(kg_item.quantity), 1.0)

        # Check invoice output has bracketed names
        inv_res = self.client.get(reverse('order_invoice', args=[order.id]))
        self.assertEqual(inv_res.status_code, 200)
        self.assertContains(inv_res, "Vanilla Dream Cake (1 kg)")
        self.assertContains(inv_res, "Croissant (1 pc)")
        self.assertContains(inv_res, "690.0")

    def test_order_with_baker_defined_weight(self):
        cake = Product.objects.create(
            seller=self.seller1,
            category=self.category,
            name="Belgian Truffle Cake",
            weight='1 kg',
            price=600.00,
            prep_time_hours=4,
            is_available=True,
        )
        self.client.force_login(self.customer)
        deliv = (timezone.now() + datetime.timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M')

        # Add 2 cakes (each 1 kg) to cart
        add_res = self.client.post(reverse('add_to_cart', args=[cake.id]), {
            'quantity': 2,
            'delivery_date': deliv,
        })
        self.assertEqual(add_res.status_code, 302)

        item = CartItem.objects.get(customer=self.customer, product=cake)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(float(item.subtotal), 1200.00)
        self.assertEqual(item.display_name, 'Belgian Truffle Cake (1 kg)')

        # Checkout
        chk_res = self.client.post(reverse('checkout'), {
            'delivery_address': 'Flat 202, Baker Street',
            'contact_number': '9876543210',
            'payment_method': 'cod',
        })
        self.assertEqual(chk_res.status_code, 302)

        order = Order.objects.filter(customer=self.customer).latest('id')
        order_item = order.items.get(product=cake)
        self.assertEqual(order_item.weight_at_order, '1 kg')
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(float(order_item.subtotal), 1200.00)
        self.assertEqual(order_item.display_name, 'Belgian Truffle Cake (1 kg)')

        # Invoice check
        inv_res = self.client.get(reverse('order_invoice', args=[order.id]))
        self.assertEqual(inv_res.status_code, 200)
        self.assertContains(inv_res, "Belgian Truffle Cake (1 kg)")

        # Seller dashboard check
        self.client.force_login(self.seller_user1)
        dash_res = self.client.get(reverse('seller_dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Belgian Truffle Cake (1 kg)")

    def test_buyer_decides_quantity_quick_add(self):
        """Verify buyer can select quantity and quick-add directly from catalog."""
        self.client.force_login(self.customer)
        # Buyer picks quantity = 3 from catalog
        res = self.client.post(reverse('add_to_cart', args=[self.product1.id]), {
            'quantity': 3,
            'quick_add': '1',
            'next': reverse('product_list'),
        })
        self.assertRedirects(res, reverse('product_list'))

        # Check cart
        item = CartItem.objects.get(customer=self.customer, product=self.product1)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(float(item.subtotal), 240.00)

        # Buyer adds 2 more of the same item
        res2 = self.client.post(reverse('add_to_cart', args=[self.product1.id]), {
            'quantity': 2,
            'quick_add': '1',
            'next': reverse('product_list'),
        })
        self.assertRedirects(res2, reverse('product_list'))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)
        self.assertEqual(float(item.subtotal), 400.00)

        # Buyer types quantity = 7 directly in cart
        res3 = self.client.post(reverse('update_cart_quantity', args=[item.id]), {
            'quantity': 7,
        })
        self.assertRedirects(res3, reverse('cart_view'))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 7)
        self.assertEqual(float(item.subtotal), 560.00)


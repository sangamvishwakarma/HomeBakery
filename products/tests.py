from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from sellers.models import Seller
from products.models import Category, Product


class ProductsTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Category
        self.category = Category.objects.create(name="Cakes")
        self.category2 = Category.objects.create(name="Cookies")

        # Create approved Seller
        self.seller_user = User.objects.create_user(
            username='seller1',
            password='Password123!',
            role='seller'
        )
        self.seller = Seller.objects.create(
            user=self.seller_user,
            business_name="Warm Oven",
            status='approved'
        )

        # Create pending Seller
        self.pending_user = User.objects.create_user(
            username='seller2',
            password='Password123!',
            role='seller'
        )
        self.pending_seller = Seller.objects.create(
            user=self.pending_user,
            business_name="Cold Oven",
            status='pending'
        )

        # Create Products
        self.product1 = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Belgian Chocolate Cake",
            price=450.00,
            description="Rich dark chocolate truffle cake",
            prep_time_hours=24,
            is_available=True,
            is_customizable=True,
        )

        self.product_pending = Product.objects.create(
            seller=self.pending_seller,
            category=self.category,
            name="Unapproved Cake",
            price=300.00,
            description="Cake from pending baker",
            prep_time_hours=12,
            is_available=True,
        )

    def test_product_list_only_approved_sellers(self):
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Belgian Chocolate Cake")
        self.assertNotContains(response, "Unapproved Cake")

    def test_product_list_filter_category(self):
        cookie = Product.objects.create(
            seller=self.seller,
            category=self.category2,
            name="Choco Chip Cookies",
            price=150.00,
            description="Crispy and chewy",
            prep_time_hours=6,
            is_available=True,
        )
        response = self.client.get(reverse('product_list') + f'?category={self.category2.id}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choco Chip Cookies")
        self.assertNotContains(response, "Belgian Chocolate Cake")

    def test_product_list_search_query(self):
        response = self.client.get(reverse('product_list') + '?q=Belgian')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Belgian Chocolate Cake")

        response_empty = self.client.get(reverse('product_list') + '?q=NonExistentBake')
        self.assertEqual(response_empty.status_code, 200)
        self.assertNotContains(response_empty, "Belgian Chocolate Cake")

    def test_product_detail_view(self):
        response = self.client.get(reverse('product_detail', args=[self.product1.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product1.name)
        self.assertContains(response, "Warm Oven")

    def test_approved_seller_add_product_get_and_post(self):
        self.client.force_login(self.seller_user)

        # GET add_product page
        get_res = self.client.get(reverse('add_product'))
        self.assertEqual(get_res.status_code, 200)
        self.assertTemplateUsed(get_res, 'products/add_product.html')

        # POST new product
        post_res = self.client.post(reverse('add_product'), {
            'category': self.category.id,
            'name': 'Red Velvet Cupcake',
            'price': '80.00',
            'description': 'Velvety cream cheese frosting',
            'prep_time_hours': 12,
            'is_customizable': 'on',
            'is_available': 'on',
        })
        self.assertEqual(post_res.status_code, 302)
        self.assertRedirects(post_res, reverse('seller_dashboard'))
        self.assertTrue(Product.objects.filter(name='Red Velvet Cupcake').exists())

    def test_pending_seller_cannot_add_product(self):
        self.client.force_login(self.pending_user)
        response = self.client.get(reverse('add_product'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('seller_dashboard'))

    def test_edit_product(self):
        self.client.force_login(self.seller_user)

        get_res = self.client.get(reverse('edit_product', args=[self.product1.id]))
        self.assertEqual(get_res.status_code, 200)
        self.assertTemplateUsed(get_res, 'products/edit_product.html')

        post_res = self.client.post(reverse('edit_product', args=[self.product1.id]), {
            'category': self.category.id,
            'name': 'Belgian Chocolate Cake Deluxe',
            'price': '500.00',
            'description': 'Updated deluxe description',
            'prep_time_hours': 24,
            'is_available': 'on',
        })
        self.assertEqual(post_res.status_code, 302)
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.name, 'Belgian Chocolate Cake Deluxe')
        self.assertEqual(self.product1.price, 500.00)

    def test_toggle_availability(self):
        self.client.force_login(self.seller_user)
        self.assertTrue(self.product1.is_available)

        response = self.client.post(reverse('toggle_availability', args=[self.product1.id]))
        self.assertEqual(response.status_code, 302)
        self.product1.refresh_from_db()
        self.assertFalse(self.product1.is_available)

    def test_delete_product(self):
        self.client.force_login(self.seller_user)
        response = self.client.post(reverse('delete_product', args=[self.product1.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(id=self.product1.id).exists())

    def test_add_product_with_weight_description(self):
        self.client.force_login(self.seller_user)
        res = self.client.post(reverse('add_product'), {
            'category': self.category.id,
            'name': 'Pineapple Gateau',
            'weight': '1 kg',
            'price': '550.00',
            'description': 'Fresh whipped cream and pineapple chunks',
            'prep_time_hours': 18,
            'is_available': 'on',
        })
        self.assertEqual(res.status_code, 302)
        p = Product.objects.get(name='Pineapple Gateau')
        self.assertEqual(p.weight, '1 kg')
        self.assertEqual(p.price, 550.00)
        self.assertEqual(p.display_name, 'Pineapple Gateau (1 kg)')
        self.assertEqual(p.price_display, '₹550.00')

        # Check detail page renders the bracketed name
        detail_res = self.client.get(reverse('product_detail', args=[p.id]))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Pineapple Gateau (1 kg)')

        # Check product list renders the bracketed name
        list_res = self.client.get(reverse('product_list'))
        self.assertEqual(list_res.status_code, 200)
        self.assertContains(list_res, 'Pineapple Gateau (1 kg)')

    def test_product_without_weight_display_name(self):
        self.assertEqual(self.product1.display_name, self.product1.name)

    def test_edit_product_with_weight(self):
        self.client.force_login(self.seller_user)
        res = self.client.post(reverse('edit_product', args=[self.product1.id]), {
            'category': self.category.id,
            'name': self.product1.name,
            'weight': '500g',
            'price': '450.00',
            'description': self.product1.description,
            'prep_time_hours': 24,
            'is_available': 'on',
        })
        self.assertEqual(res.status_code, 302)
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.weight, '500g')
        self.assertEqual(self.product1.display_name, f"{self.product1.name} (500g)")


from django.urls import path
from . import views

urlpatterns = [
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_quantity, name='update_cart_quantity'),
    path('checkout/', views.checkout, name='checkout'),
    path('payment/create-order/', views.create_payment_order, name='create_payment_order'),
    path('payment/verify/', views.verify_payment, name='verify_payment'),
    path('payment/failed/', views.payment_failed, name='payment_failed'),
    path('my-orders/', views.customer_orders, name='customer_orders'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('order/<int:order_id>/invoice/', views.order_invoice, name='order_invoice'),
    path('order/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),
    path('product/<int:product_id>/review/', views.add_review, name='add_review'),
]
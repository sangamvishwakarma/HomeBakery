from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.seller_dashboard, name='seller_dashboard'),
    path('payment-details/', views.update_payment_details, name='update_seller_payment'),
]
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg
from .models import Seller
from products.models import Product
from orders.models import Order, Review


@login_required
def seller_dashboard(request):
    try:
        seller = Seller.objects.get(user=request.user)
    except Seller.DoesNotExist:
        messages.info(request, "You do not have a seller account yet. Register here to start selling.")
        return redirect('seller_register')

    if seller.status != 'approved':
        return render(request, 'sellers/seller_dashboard.html', {'seller': seller})

    products = Product.objects.filter(seller=seller).order_by('-created_at')
    orders = Order.objects.filter(seller=seller).order_by('-order_date')

    total_earnings = sum(o.total_amount for o in orders.filter(status='delivered'))
    pending_orders = orders.filter(status='pending').count()

    rating_agg = Review.objects.filter(product__seller=seller).aggregate(Avg('rating'))
    avg_rating_raw = rating_agg['rating__avg']
    avg_rating = round(avg_rating_raw, 1) if avg_rating_raw is not None else None

    return render(request, 'sellers/seller_dashboard.html', {
        'seller': seller,
        'products': products,
        'orders': orders,
        'total_products': products.count(),
        'pending_orders': pending_orders,
        'total_earnings': total_earnings,
        'avg_rating': avg_rating,
    })
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Q
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

    settled_orders = orders.filter(Q(payment_status='paid') | Q(status='delivered')).exclude(status='cancelled')
    gross_sales = sum(o.total_amount for o in settled_orders)
    total_commission = sum(o.admin_commission for o in settled_orders)
    total_earnings = sum(o.seller_amount for o in settled_orders)
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
        'gross_sales': gross_sales,
        'total_commission': total_commission,
        'total_earnings': total_earnings,
        'avg_rating': avg_rating,
    })


@login_required
def update_payment_details(request):
    """Allows a seller to add or update their Bank Account No., IFSC, UPI ID, and Payment QR Code."""
    try:
        seller = Seller.objects.get(user=request.user)
    except Seller.DoesNotExist:
        messages.error(request, "You need a seller account to update payment details.")
        return redirect('seller_register')

    if request.method == 'POST':
        bank_account_number = request.POST.get('bank_account_number', '').strip()
        ifsc_code = request.POST.get('ifsc_code', '').strip().upper()
        upi_id = request.POST.get('upi_id', '').strip()
        payment_qr = request.FILES.get('payment_qr')

        seller.bank_account_number = bank_account_number
        seller.ifsc_code = ifsc_code
        seller.upi_id = upi_id
        if payment_qr:
            seller.payment_qr = payment_qr
        seller.save()

        messages.success(request, "Your payout details (Bank Account No., UPI ID & QR Code) have been saved!")

    return redirect('seller_dashboard')
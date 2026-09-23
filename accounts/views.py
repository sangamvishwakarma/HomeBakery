from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import User
from sellers.models import Seller
from products.models import Product, Category
from orders.models import Order
from .forms import UserRegisterForm, CustomerRegisterForm, SellerOnboardingForm, StyledAuthenticationForm


def register(request):
    """Unified registration view for all users."""
    if request.user.is_authenticated:
        return redirect('product_list')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful! Welcome to HomeBakery.")
            return redirect('product_list')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def customer_register(request):
    return register(request)


def register_choice(request):
    return register(request)


@login_required
def seller_register(request):
    """In-app onboarding for logged-in users wishing to become sellers."""
    existing_seller = Seller.objects.filter(user=request.user).first()
    if existing_seller:
        if existing_seller.status == 'approved':
            messages.info(request, "You already have an active seller account.")
            return redirect('seller_dashboard')
        elif existing_seller.status == 'pending':
            messages.info(request, "Your seller application is currently under review.")
            return redirect('seller_dashboard')

    if request.method == 'POST':
        form = SellerOnboardingForm(request.POST, user=request.user)
        if form.is_valid():
            form.save(user=request.user)
            messages.success(request, "Your seller application has been submitted and is awaiting admin approval!")
            return redirect('seller_dashboard')
    else:
        form = SellerOnboardingForm(user=request.user)

    return render(request, 'accounts/seller_register.html', {
        'form': form,
        'existing_seller': existing_seller,
    })


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = StyledAuthenticationForm


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('product_list')


# ==========================================
# Administrator Views
# ==========================================

def staff_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def admin_dashboard(request):
    if not staff_required(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('product_list')

    pending_sellers = Seller.objects.filter(status='pending').order_by('-created_at')
    all_sellers = Seller.objects.all().order_by('-created_at')
    all_orders = Order.objects.all().order_by('-order_date')[:25]
    all_users = User.objects.all().order_by('-date_joined')[:30]

    delivered_orders = Order.objects.filter(status='delivered')
    total_revenue = sum(o.total_amount for o in delivered_orders)

    context = {
        'total_users': User.objects.count(),
        'total_customers': User.objects.filter(role='customer').count(),
        'total_sellers': all_sellers.count(),
        'pending_sellers_count': pending_sellers.count(),
        'approved_sellers_count': all_sellers.filter(status='approved').count(),
        'total_products': Product.objects.count(),
        'total_orders': Order.objects.count(),
        'delivered_orders_count': delivered_orders.count(),
        'total_revenue': total_revenue,
        'pending_sellers': pending_sellers,
        'all_sellers': all_sellers,
        'all_orders': all_orders,
        'all_users': all_users,
        'categories': Category.objects.all(),
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@login_required
def admin_approve_seller(request, seller_id):
    if not staff_required(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('product_list')

    seller = get_object_or_404(Seller, id=seller_id)
    if request.method == 'POST':
        seller.status = 'approved'
        seller.save()
        messages.success(request, f"Seller '{seller.business_name}' has been approved.")
    return redirect('admin_dashboard')


@login_required
def admin_reject_seller(request, seller_id):
    if not staff_required(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('product_list')

    seller = get_object_or_404(Seller, id=seller_id)
    if request.method == 'POST':
        seller.status = 'rejected'
        seller.save()
        messages.warning(request, f"Seller '{seller.business_name}' has been rejected.")
    return redirect('admin_dashboard')


@login_required
def admin_toggle_user_status(request, user_id):
    if not staff_required(request.user):
        messages.error(request, "Access denied. Administrator privileges required.")
        return redirect('product_list')

    user_obj = get_object_or_404(User, id=user_id)
    if user_obj == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('admin_dashboard')

    if request.method == 'POST':
        user_obj.is_active = not user_obj.is_active
        user_obj.save()
        status_text = "activated" if user_obj.is_active else "deactivated"
        messages.info(request, f"User '{user_obj.username}' has been {status_text}.")
    return redirect('admin_dashboard')
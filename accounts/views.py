import datetime
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from .models import User, OTPVerification
from sellers.models import Seller
from products.models import Product, Category
from orders.models import Order
from .forms import (
    UserRegisterForm,
    CustomerRegisterForm,
    OTPVerificationForm,
    SellerOnboardingForm,
    StyledAuthenticationForm,
)

logger = logging.getLogger(__name__)


def mask_email(email):
    if not email or '@' not in email:
        return email
    user_part, domain = email.split('@', 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + '*'
    else:
        masked_user = user_part[:2] + '*' * (len(user_part) - 2)
    return f"{masked_user}@{domain}"


def mask_phone(phone):
    if not phone or len(phone) < 4:
        return phone
    return '*' * (len(phone) - 4) + phone[-4:]


def register(request):
    """Unified registration view for all users with Email and Phone OTP verification."""
    if request.user.is_authenticated:
        return redirect('product_list')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            pending_data = {
                'username': form.cleaned_data['username'],
                'email': form.cleaned_data['email'],
                'phone': form.cleaned_data['phone'],
                'address': form.cleaned_data['address'],
                'password': form.cleaned_data['password1'],
            }

            email_otp = OTPVerification.generate_otp()
            phone_otp = OTPVerification.generate_otp()
            expires_at = timezone.now() + datetime.timedelta(minutes=10)

            otp_record = OTPVerification.objects.create(
                email=pending_data['email'],
                phone=pending_data['phone'],
                email_otp=email_otp,
                phone_otp=phone_otp,
                expires_at=expires_at,
            )

            request.session['pending_registration'] = pending_data
            request.session['otp_id'] = otp_record.id

            # Send Email OTP
            try:
                send_mail(
                    subject='Your HomeBakery Verification Code',
                    message=(
                        f"Hello {pending_data['username']},\n\n"
                        f"Your email verification code for HomeBakery is: {email_otp}\n\n"
                        f"This code will expire in 10 minutes.\n\n"
                        f"Warm regards,\nHomeBakery Team"
                    ),
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@homebakery.com'),
                    recipient_list=[pending_data['email']],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Failed to send email OTP: {e}")

            # Send/Simulate Phone OTP
            logger.info(f"[SMS OTP] Sent phone verification code {phone_otp} to {pending_data['phone']}")
            print(f"[SMS OTP] Verification code for {pending_data['phone']} is: {phone_otp}")

            messages.info(
                request,
                f"Verification codes sent to {pending_data['email']} and {pending_data['phone']}. "
                "Please enter both codes below to complete your registration."
            )
            return redirect('verify_otp')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def customer_register(request):
    return register(request)


def register_choice(request):
    return register(request)



def verify_otp(request):
    """Verifies Email OTP and Phone OTP before creating the user account."""
    if request.user.is_authenticated:
        return redirect('product_list')

    pending_data = request.session.get('pending_registration')
    otp_id = request.session.get('otp_id')

    if not pending_data or not otp_id:
        messages.warning(request, "No pending registration found. Please register first.")
        return redirect('register')

    try:
        otp_record = OTPVerification.objects.get(id=otp_id, is_used=False)
    except OTPVerification.DoesNotExist:
        messages.error(request, "Verification session expired or already completed. Please register again.")
        return redirect('register')

    if request.method == 'POST':
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            entered_email_otp = form.cleaned_data['email_otp'].strip()
            entered_phone_otp = form.cleaned_data['phone_otp'].strip()

            if otp_record.is_expired():
                messages.error(request, "Your verification codes have expired. Please click 'Resend OTPs'.")
            else:
                email_valid = (entered_email_otp == otp_record.email_otp)
                phone_valid = (entered_phone_otp == otp_record.phone_otp)

                if not email_valid and not phone_valid:
                    form.add_error('email_otp', "Invalid Email verification code.")
                    form.add_error('phone_otp', "Invalid Phone verification code.")
                elif not email_valid:
                    form.add_error('email_otp', "Invalid Email verification code. Please check your inbox.")
                elif not phone_valid:
                    form.add_error('phone_otp', "Invalid Phone verification code. Please check your messages.")
                else:
                    # Both valid! Create user
                    otp_record.is_used = True
                    otp_record.save()

                    user = User.objects.create_user(
                        username=pending_data['username'],
                        email=pending_data['email'],
                        password=pending_data['password'],
                        phone=pending_data['phone'],
                        address=pending_data['address'],
                        role='customer',
                        is_email_verified=True,
                        is_phone_verified=True,
                    )

                    request.session.pop('pending_registration', None)
                    request.session.pop('otp_id', None)

                    login(request, user)
                    messages.success(request, f"Welcome to HomeBakery, {user.username}! Your email and phone have been verified successfully.")
                    return redirect('product_list')
    else:
        form = OTPVerificationForm()

    raw_email = pending_data.get('email', '')
    raw_phone = pending_data.get('phone', '')

    return render(request, 'accounts/verify_otp.html', {
        'form': form,
        'email': raw_email,
        'phone': raw_phone,
        'masked_email': mask_email(raw_email),
        'masked_phone': mask_phone(raw_phone),
        'otp_record': otp_record,
        'debug_mode': settings.DEBUG,
    })


def resend_otp(request):
    """Generates and resends fresh verification codes to the pending user's email and phone."""
    if request.user.is_authenticated:
        return redirect('product_list')

    pending_data = request.session.get('pending_registration')
    if not pending_data:
        messages.warning(request, "No pending registration found. Please register first.")
        return redirect('register')

    new_email_otp = OTPVerification.generate_otp()
    new_phone_otp = OTPVerification.generate_otp()
    new_expires = timezone.now() + datetime.timedelta(minutes=10)

    otp_record = OTPVerification.objects.create(
        email=pending_data['email'],
        phone=pending_data['phone'],
        email_otp=new_email_otp,
        phone_otp=new_phone_otp,
        expires_at=new_expires,
    )
    request.session['otp_id'] = otp_record.id

    try:
        send_mail(
            subject='Your New HomeBakery Verification Code',
            message=(
                f"Hello {pending_data['username']},\n\n"
                f"Your new email verification code for HomeBakery is: {new_email_otp}\n\n"
                f"This code will expire in 10 minutes.\n\n"
                f"Warm regards,\nHomeBakery Team"
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@homebakery.com'),
            recipient_list=[pending_data['email']],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f"Failed to resend email OTP: {e}")

    logger.info(f"[SMS OTP] Resent phone verification code {new_phone_otp} to {pending_data['phone']}")
    print(f"[SMS OTP] New verification code for {pending_data['phone']} is: {new_phone_otp}")

    messages.success(request, f"New verification codes sent to {pending_data['email']} and {pending_data['phone']}.")
    return redirect('verify_otp')


def cancel_registration(request):
    """Clears pending registration from session and redirects to registration form."""
    request.session.pop('pending_registration', None)
    request.session.pop('otp_id', None)
    messages.info(request, "Registration cancelled. You can register with fresh details.")
    return redirect('register')



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
        form = SellerOnboardingForm(request.POST, request.FILES, user=request.user)
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

    from django.db.models import Q
    pending_sellers = Seller.objects.filter(status='pending').order_by('-created_at')
    all_sellers = Seller.objects.all().order_by('-created_at')
    all_orders = Order.objects.all().order_by('-order_date')[:25]
    all_users = User.objects.all().order_by('-date_joined')[:30]

    delivered_orders = Order.objects.filter(status='delivered')
    settled_orders = Order.objects.filter(Q(payment_status='paid') | Q(status='delivered')).exclude(status='cancelled')
    total_revenue = sum(o.total_amount for o in settled_orders)
    total_admin_commission = sum(o.admin_commission for o in settled_orders)
    total_seller_payout = sum(o.seller_amount for o in settled_orders)

    for s in all_sellers:
        s_settled = s.orders.filter(Q(payment_status='paid') | Q(status='delivered')).exclude(status='cancelled')
        s.gross_sales = sum(o.total_amount for o in s_settled)
        s.admin_commission_total = sum(o.admin_commission for o in s_settled)
        s.net_payout = sum(o.seller_amount for o in s_settled)

    context = {
        'total_users': User.objects.count(),
        'total_customers': User.objects.filter(role='customer').count(),
        'total_sellers': all_sellers.count(),
        'pending_sellers_count': pending_sellers.count(),
        'approved_sellers_count': all_sellers.filter(status='approved').count(),
        'total_products': Product.objects.count(),
        'total_orders': Order.objects.count(),
        'delivered_orders_count': delivered_orders.count(),
        'paid_orders_count': settled_orders.count(),
        'total_revenue': total_revenue,
        'total_admin_commission': total_admin_commission,
        'total_seller_payout': total_seller_payout,
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
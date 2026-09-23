import datetime
import json
import hmac
import hashlib
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.conf import settings
from django.urls import reverse
from .models import CartItem, Order, OrderItem, Review, Payment
from products.models import Product

try:
    import razorpay
except ImportError:
    razorpay = None

DELIVERY_FEE = 30


def generate_sandbox_signature(order_id, payment_id):
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret_homebakery456')
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    return hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def verify_razorpay_signature(order_id, payment_id, signature):
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret_homebakery456')
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    expected = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)

    if request.method == 'POST':
        unit = 'piece'
        try:
            quantity = Decimal(str(request.POST.get('quantity', 1)))
            if quantity < 1:
                quantity = Decimal('1')
        except (ValueError, TypeError, InvalidOperation):
            quantity = Decimal('1')

        # Parse delivery date
        delivery_date_raw = request.POST.get('delivery_date', '').strip()
        is_quick_add = request.POST.get('quick_add') == '1'

        if not delivery_date_raw:
            if is_quick_add:
                # Default delivery date for catalog quick-add: prep notice window rounded up
                now = timezone.now()
                target = now + datetime.timedelta(hours=product.prep_time_hours + 1)
                deliv_dt = target.replace(minute=0, second=0, microsecond=0)
            else:
                messages.error(request, "Please select a preferred delivery date and time.")
                return redirect('product_detail', product_id=product_id)
        else:
            try:
                deliv_dt = parse_datetime(delivery_date_raw)
                if not deliv_dt:
                    raise ValueError("Invalid date format")
                if timezone.is_naive(deliv_dt):
                    deliv_dt = timezone.make_aware(deliv_dt)
            except Exception:
                messages.error(request, "Invalid delivery date format.")
                return redirect('product_detail', product_id=product_id)

            # Validate prep time window
            min_delivery_time = timezone.now() + datetime.timedelta(hours=product.prep_time_hours)
            if deliv_dt < min_delivery_time:
                messages.error(
                    request,
                    f"Delivery date must be at least {product.prep_time_hours} hours from now to allow for fresh preparation."
                )
                return redirect('product_detail', product_id=product_id)

        customization_notes = request.POST.get('customization_notes', '').strip()

        # Check if identical item already in cart
        existing_item = CartItem.objects.filter(
            customer=request.user,
            product=product,
            unit=unit,
            customization_notes=customization_notes,
        ).first() if is_quick_add else CartItem.objects.filter(
            customer=request.user,
            product=product,
            unit=unit,
            customization_notes=customization_notes,
            delivery_date=deliv_dt,
        ).first()

        if existing_item:
            existing_item.quantity += quantity
            existing_item.save()
            messages.success(request, f"Updated quantity for '{product.display_name}' ({existing_item.formatted_quantity}) in your cart.")
        else:
            new_item = CartItem.objects.create(
                customer=request.user,
                product=product,
                unit=unit,
                quantity=quantity,
                customization_notes=customization_notes,
                delivery_date=deliv_dt,
            )
            messages.success(request, f"Added '{product.display_name}' ({new_item.formatted_quantity}) to your cart!")

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('cart_view')

    return redirect('product_detail', product_id=product_id)


@login_required
def cart_view(request):
    cart_items = CartItem.objects.filter(customer=request.user)
    sellers = {item.product.seller for item in cart_items}
    total_delivery_fee = DELIVERY_FEE * len(sellers) if cart_items else 0
    cart_total = sum(item.subtotal for item in cart_items)
    grand_total = cart_total + total_delivery_fee

    return render(request, 'orders/cart.html', {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'delivery_fee': total_delivery_fee,
        'grand_total': grand_total,
        'seller_count': len(sellers),
    })


@login_required
def update_cart_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, customer=request.user)
    step = Decimal('1')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'increase':
            item.quantity += step
            item.save()
        elif action == 'decrease':
            if item.quantity > step:
                item.quantity -= step
                item.save()
            else:
                item.delete()
                messages.info(request, f"Removed '{item.product.name}' from cart.")
                return redirect('cart_view')
        elif 'quantity' in request.POST:
            try:
                new_qty = Decimal(str(request.POST['quantity']))
                if new_qty > 0:
                    item.quantity = new_qty
                    item.save()
                else:
                    item.delete()
                    messages.info(request, f"Removed '{item.product.name}' from cart.")
                    return redirect('cart_view')
            except (ValueError, TypeError, InvalidOperation):
                pass
    return redirect('cart_view')


@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, customer=request.user)
    name = item.product.name
    item.delete()
    messages.info(request, f"Removed '{name}' from your cart.")
    return redirect('cart_view')


@login_required
def checkout(request):
    cart_items = CartItem.objects.filter(customer=request.user)
    if not cart_items:
        messages.warning(request, "Your cart is empty.")
        return redirect('product_list')

    sellers = {item.product.seller for item in cart_items}
    total_delivery_fee = DELIVERY_FEE * len(sellers)
    cart_total = sum(item.subtotal for item in cart_items)
    grand_total = cart_total + total_delivery_fee
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_homebakery123')

    if request.method == 'POST':
        delivery_address = request.POST.get('delivery_address', '').strip()
        contact_number = request.POST.get('contact_number', '').strip()
        payment_method = request.POST.get('payment_method', 'cod')

        if not delivery_address or not contact_number:
            messages.error(request, "Please enter both delivery address and contact number.")
            return render(request, 'orders/checkout.html', {
                'cart_items': cart_items,
                'cart_total': cart_total,
                'delivery_fee': total_delivery_fee,
                'grand_total': grand_total,
                'razorpay_key_id': key_id,
            })

        valid_payment_methods = [code for code, _ in Order.PAYMENT_CHOICES]
        if payment_method not in valid_payment_methods:
            payment_method = 'cod'

        if payment_method == 'cod':
            cod_ref = f"COD-{request.user.id}-{int(timezone.now().timestamp())}"
            first_order = None
            with transaction.atomic():
                for seller in sellers:
                    seller_items = cart_items.filter(product__seller=seller)
                    seller_total = sum(item.subtotal for item in seller_items) + DELIVERY_FEE

                    order = Order.objects.create(
                        customer=request.user,
                        seller=seller,
                        delivery_address=delivery_address,
                        contact_number=contact_number,
                        payment_method='cod',
                        payment_status='pending',
                        transaction_id=cod_ref,
                        delivery_date=seller_items.first().delivery_date,
                        total_amount=seller_total,
                    )
                    if not first_order:
                        first_order = order

                    for item in seller_items:
                        OrderItem.objects.create(
                            order=order,
                            product=item.product,
                            quantity=item.quantity,
                            unit=item.unit,
                            weight_at_order=item.product.weight or '',
                            price_at_order=item.unit_price,
                            customization_notes=item.customization_notes,
                        )

                Payment.objects.create(
                    customer=request.user,
                    amount=grand_total,
                    gateway='cod',
                    payment_method='cod',
                    razorpay_order_id=cod_ref,
                    status='successful',
                )

                cart_items.delete()

            messages.success(request, "Order placed successfully! Track your order details below.")
            return redirect('customer_orders')
        else:
            messages.info(request, "Please complete payment using the payment button below.")
            return redirect('checkout')

    return render(request, 'orders/checkout.html', {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'delivery_fee': total_delivery_fee,
        'grand_total': grand_total,
        'razorpay_key_id': key_id,
    })


@login_required
def create_payment_order(request):
    """
    Creates a Razorpay Order ID (or sandbox order) and initializes a Payment record.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    cart_items = CartItem.objects.filter(customer=request.user)
    if not cart_items:
        return JsonResponse({'status': 'error', 'message': 'Your cart is empty.'}, status=400)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    delivery_address = data.get('delivery_address', '').strip()
    contact_number = data.get('contact_number', '').strip()
    payment_method = data.get('payment_method', 'upi')

    if not delivery_address or not contact_number:
        return JsonResponse({'status': 'error', 'message': 'Please provide delivery address and contact number.'}, status=400)

    sellers = {item.product.seller for item in cart_items}
    total_delivery_fee = DELIVERY_FEE * len(sellers)
    cart_total = sum(item.subtotal for item in cart_items)
    grand_total = cart_total + total_delivery_fee
    amount_in_paise = int(grand_total * 100)

    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_homebakery123')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret_homebakery456')

    is_sandbox = True
    razorpay_order_id = f"order_test_{int(timezone.now().timestamp())}_{request.user.id}"

    # If real razorpay client is available and key is configured, try creating a real Razorpay order
    if razorpay and key_id and not key_id.startswith('rzp_test_homebakery'):
        try:
            client = razorpay.Client(auth=(key_id, key_secret))
            rp_order = client.order.create({
                'amount': amount_in_paise,
                'currency': 'INR',
                'payment_capture': '1',
                'notes': {
                    'customer_id': str(request.user.id),
                    'customer_name': request.user.username,
                }
            })
            razorpay_order_id = rp_order['id']
            is_sandbox = False
        except Exception:
            is_sandbox = True

    payment = Payment.objects.create(
        customer=request.user,
        amount=grand_total,
        gateway='razorpay',
        payment_method=payment_method,
        razorpay_order_id=razorpay_order_id,
        status='initiated',
    )

    simulated_payment_id = f"pay_test_{int(timezone.now().timestamp())}_{payment.id}"
    simulated_signature = generate_sandbox_signature(razorpay_order_id, simulated_payment_id)

    return JsonResponse({
        'status': 'success',
        'payment_id': payment.id,
        'razorpay_order_id': razorpay_order_id,
        'amount': float(grand_total),
        'amount_in_paise': amount_in_paise,
        'currency': 'INR',
        'key_id': key_id,
        'is_sandbox': is_sandbox,
        'simulated_payment_id': simulated_payment_id,
        'simulated_signature': simulated_signature,
        'customer_name': request.user.username,
        'customer_email': request.user.email or '',
        'customer_phone': contact_number,
        'business_name': 'HomeBakery',
        'description': f'Fresh bakery order for ₹{grand_total}',
    })


@login_required
def verify_payment(request):
    """
    Verifies payment signature from Razorpay or sandbox simulator.
    On valid signature, atomically creates Order and OrderItem records,
    marks payment as successful, and clears the cart.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    razorpay_order_id = data.get('razorpay_order_id', '').strip()
    razorpay_payment_id = data.get('razorpay_payment_id', '').strip()
    razorpay_signature = data.get('razorpay_signature', '').strip()
    delivery_address = data.get('delivery_address', '').strip()
    contact_number = data.get('contact_number', '').strip()
    payment_method = data.get('payment_method', 'upi')

    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return JsonResponse({'status': 'error', 'message': 'Missing payment verification parameters.'}, status=400)

    is_valid = verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)
    payment = Payment.objects.filter(customer=request.user, razorpay_order_id=razorpay_order_id).order_by('-created_at').first()

    if not is_valid:
        if payment:
            payment.status = 'failed'
            payment.razorpay_payment_id = razorpay_payment_id
            payment.razorpay_signature = razorpay_signature
            payment.error_message = 'Signature verification failed.'
            payment.save()
        return JsonResponse({'status': 'error', 'message': 'Payment signature verification failed. Your account was not charged.'}, status=400)

    cart_items = CartItem.objects.filter(customer=request.user)
    if not cart_items:
        return JsonResponse({'status': 'error', 'message': 'Cart is empty or already processed.'}, status=400)

    sellers = {item.product.seller for item in cart_items}

    with transaction.atomic():
        created_orders = []
        for seller in sellers:
            seller_items = cart_items.filter(product__seller=seller)
            seller_total = sum(item.subtotal for item in seller_items) + DELIVERY_FEE

            order = Order.objects.create(
                customer=request.user,
                seller=seller,
                delivery_address=delivery_address or request.user.address,
                contact_number=contact_number or request.user.phone,
                payment_method=payment_method,
                payment_status='paid',
                transaction_id=razorpay_payment_id,
                paid_at=timezone.now(),
                delivery_date=seller_items.first().delivery_date,
                total_amount=seller_total,
            )
            created_orders.append(order)

            for item in seller_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    unit=item.unit,
                    weight_at_order=item.product.weight or '',
                    price_at_order=item.unit_price,
                    customization_notes=item.customization_notes,
                )

        if payment:
            payment.status = 'successful'
            payment.razorpay_payment_id = razorpay_payment_id
            payment.razorpay_signature = razorpay_signature
            payment.payment_method = payment_method
            payment.save()

        cart_items.delete()

    first_order_id = created_orders[0].id if created_orders else None
    messages.success(request, f"Payment received successfully! Your order #{first_order_id} has been placed.")
    return JsonResponse({
        'status': 'success',
        'order_id': first_order_id,
        'redirect_url': reverse('order_detail', kwargs={'order_id': first_order_id}) if first_order_id else reverse('customer_orders'),
    })


@login_required
def payment_failed(request):
    order_id = request.GET.get('order_id') or request.POST.get('order_id')
    reason = request.GET.get('reason') or request.POST.get('reason') or 'Payment was cancelled or could not be completed.'

    if order_id:
        payment = Payment.objects.filter(customer=request.user, razorpay_order_id=order_id).first()
        if payment:
            payment.status = 'failed'
            payment.error_message = reason
            payment.save()

    messages.error(request, f"Payment failed: {reason} Please try again or select Cash on Delivery.")
    return redirect('checkout')


@login_required
def order_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    is_seller = hasattr(request.user, 'seller') and order.seller == request.user.seller
    is_customer = order.customer == request.user
    if not (is_customer or is_seller or request.user.is_staff):
        messages.error(request, "You do not have permission to view or print this bill/invoice.")
        return redirect('customer_orders')

    items_subtotal = sum(item.subtotal for item in order.items.all())
    delivery_fee = order.total_amount - items_subtotal

    return render(request, 'orders/order_invoice.html', {
        'order': order,
        'items_subtotal': items_subtotal,
        'delivery_fee': delivery_fee,
        'is_seller': is_seller,
        'is_customer': is_customer,
    })


@login_required
def customer_orders(request):
    orders = Order.objects.filter(customer=request.user).order_by('-order_date')
    return render(request, 'orders/my_orders.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    # Ensure only customer, seller of this order, or staff can view
    is_seller = hasattr(request.user, 'seller') and order.seller == request.user.seller
    is_customer = order.customer == request.user
    if not (is_customer or is_seller or request.user.is_staff):
        messages.error(request, "You do not have permission to view this order.")
        return redirect('product_list')

    return render(request, 'orders/order_detail.html', {
        'order': order,
        'is_seller': is_seller,
    })


@login_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, seller__user=request.user)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = [s[0] for s in Order.STATUS_CHOICES]
        if new_status in valid_statuses:
            order.status = new_status
            order.save()
            messages.success(request, f"Order #{order.id} status changed to {order.get_status_display()}.")
        else:
            messages.error(request, "Invalid order status specified.")
    return redirect('seller_dashboard')


@login_required
def add_review(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        try:
            rating = int(request.POST.get('rating', 5))
            if rating < 1 or rating > 5:
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        comment = request.POST.get('comment', '').strip()
        Review.objects.update_or_create(
            customer=request.user,
            product=product,
            defaults={'rating': rating, 'comment': comment},
        )
        messages.success(request, f"Thank you! Your review for '{product.name}' has been saved.")

    return redirect('product_detail', product_id=product.id)
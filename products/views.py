from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product, Category
from .forms import ProductForm
from sellers.models import Seller


def product_list(request):
    products = Product.objects.filter(seller__status='approved')

    query = request.GET.get('q')
    if query:
        products = products.filter(name__icontains=query.strip())

    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)

    categories = Category.objects.all()
    return render(request, 'products/product_list.html', {
        'products': products,
        'categories': categories,
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'products/product_detail.html', {'product': product})


@login_required
def add_product(request):
    try:
        seller = Seller.objects.get(user=request.user, status='approved')
    except Seller.DoesNotExist:
        messages.error(request, "Only approved sellers can add products.")
        return redirect('seller_dashboard')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = seller
            product.save()
            messages.success(request, f"Product '{product.name}' added successfully!")
            return redirect('seller_dashboard')
    else:
        form = ProductForm()

    categories = Category.objects.all()
    return render(request, 'products/add_product.html', {'form': form, 'categories': categories})


@login_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller__user=request.user)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Product '{product.name}' updated successfully!")
            return redirect('seller_dashboard')
    else:
        form = ProductForm(instance=product)

    categories = Category.objects.all()
    return render(request, 'products/edit_product.html', {'form': form, 'product': product, 'categories': categories})


@login_required
def toggle_availability(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller__user=request.user)
    if request.method == 'POST':
        product.is_available = not product.is_available
        product.save()
        status_str = "available" if product.is_available else "unavailable"
        messages.success(request, f"'{product.name}' marked as {status_str}.")
    return redirect('seller_dashboard')


@login_required
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller__user=request.user)
    if request.method == 'POST':
        name = product.name
        product.delete()
        messages.success(request, f"Product '{name}' was deleted.")
    return redirect('seller_dashboard')
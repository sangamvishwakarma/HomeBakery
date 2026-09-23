from .models import CartItem


def cart_context(request):
    if hasattr(request, 'user') and request.user.is_authenticated and getattr(request.user, 'role', '') == 'customer':
        return {
            'cart_item_count': CartItem.objects.filter(customer=request.user).count()
        }
    return {
        'cart_item_count': 0
    }


from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('register/choice/', views.register_choice, name='register_choice'),
    path('register/customer/', views.customer_register, name='customer_register'),
    path('register/seller/', views.seller_register, name='seller_register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Admin Views
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/seller/<int:seller_id>/approve/', views.admin_approve_seller, name='admin_approve_seller'),
    path('admin-dashboard/seller/<int:seller_id>/reject/', views.admin_reject_seller, name='admin_reject_seller'),
    path('admin-dashboard/user/<int:user_id>/toggle/', views.admin_toggle_user_status, name='admin_toggle_user_status'),
]
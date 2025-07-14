from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/',    views.LoginView.as_view(),    name='login'),
    path('logout/',   views.LogoutView.as_view(),   name='logout'),

    path('dashboard/', views.dashboard_router,      name='dashboard'),
    path('dashboard/client/',  views.client_dashboard,  name='client'),
    path('dashboard/master/',  views.master_dashboard,  name='master'),
    path('dashboard/admin/',   views.admin_dashboard,   name='admin'),
]

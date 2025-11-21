from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('weather/', views.weather_view, name='weather'),
    path('community/', views.community_view, name='community'),
    path('scan/', views.scan_view, name='scan'),
    path('chatbot/', views.chatbot_view, name='chatbot'),
    path('market/', views.market_view, name='market'),
]

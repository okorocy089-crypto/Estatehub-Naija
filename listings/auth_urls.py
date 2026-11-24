from django.urls import path

from . import auth_views

app_name = 'auth'

urlpatterns = [
    path('me/', auth_views.current_user, name='current_user'),
    path('register/', auth_views.register, name='register'),
    path('login/', auth_views.login_view, name='login'),
    path('google/', auth_views.google_login, name='google_login'),
    path('logout/', auth_views.logout_view, name='logout'),
]

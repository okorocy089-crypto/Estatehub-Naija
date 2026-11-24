from django.urls import path
from . import views
from . import auth_views

app_name = 'listings'

urlpatterns = [
    path('', views.property_list_view, name='property_list'),
    path('saved-properties/', views.saved_properties, name='saved_properties'),
    path('saved-searches/', views.saved_searches, name='saved_searches'),
    path('saved-searches/save/', views.save_search, name='save_search'),
    path('saved-searches/<int:search_id>/<slug:action>/', views.saved_search_action, name='saved_search_action'),
    path('info/<slug:slug>/', views.site_info_page, name='site_info'),
    path('register/', auth_views.register_page, name='auth_register'),
    path('login/', auth_views.login_page, name='auth_login'),
    path('logout/', auth_views.logout_page, name='auth_logout'),
    path('agents/register/', auth_views.agent_registration, name='agent_registration'),
    path('agents/verify-email/', auth_views.agent_email_verify, name='agent_email_verify'),
    path('agents/details/', auth_views.agent_details, name='agent_details'),
    path('google/profile/', auth_views.google_profile_completion, name='google_profile_completion'),
    path('password-reset/', auth_views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/', auth_views.password_reset_verify, name='password_reset_verify'),
    path('password-reset/new/', auth_views.password_reset_new, name='password_reset_new'),
    path('property/add/', views.PropertyCreateView.as_view(), name='property_create'),
    path('property/<slug:slug>/', views.property_detail_view, name='property_detail'),
    path('property/<slug:slug>/save/', views.toggle_favorite, name='toggle_favorite'),
    path('dashboard/', views.AgentDashboardView.as_view(), name='agent_dashboard'),
    path('property/<slug:slug>/mark-complete/', views.property_mark_complete, name='property_mark_complete'),
    path('property/<slug:slug>/edit/', views.PropertyUpdateView.as_view(), name='property_update'),
    path('property/<slug:slug>/delete/', views.PropertyDeleteView.as_view(), name='property_delete'),
]

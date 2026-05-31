from django.contrib.auth import views as auth_views
from django.urls import path

from .views import ServiceNowLoginView

urlpatterns = [
    path("login/", ServiceNowLoginView.as_view(), name="accounts-login"),
    path("logout/", auth_views.LogoutView.as_view(), name="accounts-logout"),
]
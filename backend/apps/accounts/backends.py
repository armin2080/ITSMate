from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from requests import RequestException

from apps.servicenow.client import ServiceNowClient


class ServiceNowAuthenticationBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        login_name = str(username or kwargs.get("email") or "").strip()
        secret = str(password or "").strip()
        if not login_name or not secret:
            return None

        client = ServiceNowClient(username=login_name, password=secret)
        try:
            user_record = client.get_user_record(login_name)
        except RequestException:
            return None

        if not user_record:
            return None

        user_model = get_user_model()
        resolved_username = str(user_record.get("user_name") or login_name).strip()
        user, _ = user_model.objects.get_or_create(username=resolved_username)
        display_name = str(user_record.get("name") or "").strip()
        first_name, last_name = self._split_display_name(display_name)
        if first_name != user.first_name or last_name != user.last_name:
            user.first_name = first_name
            user.last_name = last_name
        email = str(user_record.get("email") or "").strip()
        if email and email != user.email:
            user.email = email
        user.set_unusable_password()
        user.save(update_fields=["first_name", "last_name", "email", "password"])
        return user

    def get_user(self, user_id):
        user_model = get_user_model()
        try:
            return user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist:
            return None

    def _split_display_name(self, display_name: str) -> tuple[str, str]:
        if not display_name:
            return "", ""
        parts = display_name.split(None, 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]
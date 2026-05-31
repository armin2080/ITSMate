from __future__ import annotations

from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView

from apps.audit.services import AuditService


class ServiceNowLoginView(TemplateView):
    template_name = "registration/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            next_target = request.GET.get("next") or reverse("teams-chat-tester")
            if not url_has_allowed_host_and_scheme(next_target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                next_target = reverse("teams-chat-tester")
            return redirect(next_target)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "logout_url": reverse("accounts-logout"),
                "next_url": self.request.GET.get("next") or reverse("teams-chat-tester"),
                "username": self.request.POST.get("username", ""),
                "error_message": self.request.GET.get("error", ""),
                "error_description": self.request.GET.get("error_description", ""),
            }
        )
        return context

    def post(self, request):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        next_url = request.POST.get("next") or reverse("teams-chat-tester")

        user = authenticate(request, username=username, password=password)
        if user is None:
            context = self.get_context_data()
            context["username"] = username
            context["error_message"] = "Login failed."
            context["error_description"] = "Check your ServiceNow username and password, then try again."
            return render(request, self.template_name, context, status=400)

        login(request, user)
        request.session["servicenow_username"] = user.get_username()
        request.session["servicenow_password"] = password
        AuditService().update_profile(
            user_identifier=user.get_username(),
            servicenow_username=user.get_username(),
        )

        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse("teams-chat-tester")
        return redirect(next_url)
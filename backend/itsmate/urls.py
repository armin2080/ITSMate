"""Root URL configuration for ITSMate."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.views.generic import RedirectView


def health_check(_request):
    return JsonResponse({"status": "ok", "service": "ITSMate"})


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="teams-chat-tester", permanent=False)),
    path("admin/", admin.site.urls),
    path("health/", health_check),
    path("api/teams/", include("apps.teams.urls")),
    path("feedback/", include("apps.feedback.urls")),
]

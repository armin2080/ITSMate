from django.urls import path

from .views import TeamsWebhookView, TeamsChatTesterView, TeamsUserProfileView, TeamsInsightsView, TeamsChatHistoryView

urlpatterns = [
    path("chat/", TeamsChatTesterView.as_view(), name="teams-chat-tester"),
    path("chat-history/", TeamsChatHistoryView.as_view(), name="teams-chat-history"),
    path("profile/", TeamsUserProfileView.as_view(), name="teams-profile"),
    path("insights/", TeamsInsightsView.as_view(), name="teams-insights"),
    path("webhook/", TeamsWebhookView.as_view(), name="teams-webhook"),
]

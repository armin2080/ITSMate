from django.urls import path

from .views import feedback_list, submit_feedback, FeedbackThanksView

urlpatterns = [
    path("", submit_feedback, name="feedback-submit"),
    path("admin/", feedback_list, name="feedback-list"),
    path("thanks/", FeedbackThanksView.as_view(), name="feedback-thanks"),
]

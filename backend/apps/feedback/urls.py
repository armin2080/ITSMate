from django.urls import path

from .views import submit_feedback, FeedbackThanksView

urlpatterns = [
    path("", submit_feedback, name="feedback-submit"),
    path("thanks/", FeedbackThanksView.as_view(), name="feedback-thanks"),
]

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Feedback


@override_settings(SERVICENOW_USERNAME="admin")
class FeedbackListTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(username="admin")
        self.regular_user = user_model.objects.create_user(username="someone-else")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("feedback-list"))

        self.assertRedirects(
            response,
            f"{reverse('accounts-login')}?next={reverse('feedback-list')}",
        )

    def test_non_admin_user_is_forbidden(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("feedback-list"))

        self.assertEqual(response.status_code, 403)

    def test_configured_admin_can_view_feedback_newest_first(self):
        older = Feedback.objects.create(message="Older feedback")
        newer = Feedback.objects.create(name="Ada", email="ada@example.com", message="Newer feedback")
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("feedback-list"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["feedbacks"], [newer, older])
        self.assertContains(response, "Newer feedback")
        self.assertContains(response, "Older feedback")

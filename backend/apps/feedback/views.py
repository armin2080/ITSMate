from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from .forms import FeedbackForm
from .models import Feedback


@require_http_methods(["GET", "POST"])
def submit_feedback(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            form.save()
            # return JSON for AJAX submissions
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": "Thank you for your feedback."})
            return redirect("feedback-thanks")
        else:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors}, status=400)
    else:
        form = FeedbackForm()
    return render(request, "feedback/submit_feedback.html", {"form": form})


@login_required
def feedback_list(request):
    admin_username = settings.SERVICENOW_USERNAME.strip()
    if not admin_username or request.user.get_username() != admin_username:
        raise PermissionDenied

    return render(
        request,
        "feedback/feedback_list.html",
        {"feedbacks": Feedback.objects.order_by("-created_at")},
    )


class FeedbackThanksView(TemplateView):
    template_name = "feedback/thanks.html"

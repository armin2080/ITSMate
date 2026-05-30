from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from .forms import FeedbackForm


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


class FeedbackThanksView(TemplateView):
    template_name = "feedback/thanks.html"

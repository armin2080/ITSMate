from django import forms

from .models import Feedback


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["name", "email", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 6})}

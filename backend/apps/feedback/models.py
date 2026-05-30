from django.db import models


class Feedback(models.Model):
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"Feedback from {self.name or self.email or 'anonymous'} on {self.created_at:%Y-%m-%d}"

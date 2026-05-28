from django.db import models


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user_identifier = models.CharField(max_length=255)
    original_message = models.TextField()
    detected_intent = models.CharField(max_length=64)
    parameters = models.JSONField(default=dict, blank=True)
    service_now_action = models.CharField(max_length=128)
    success = models.BooleanField(default=False)
    response_summary = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.timestamp.isoformat()} - {self.user_identifier} - {self.detected_intent}"


class UserProfile(models.Model):
    user_identifier = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255, blank=True, default="")
    servicenow_username = models.CharField(max_length=255, blank=True, default="")
    preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        label = self.display_name or self.user_identifier
        return f"{label} ({self.user_identifier})"

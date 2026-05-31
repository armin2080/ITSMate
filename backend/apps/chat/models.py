from django.db import models


class ChatConversation(models.Model):
    conversation_id = models.CharField(max_length=255, unique=True)
    user_identifier = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, default="")
    pending_service_now_action = models.CharField(max_length=128, blank=True, default="")
    pending_service_now_parameters = models.JSONField(default=dict, blank=True)
    pending_service_now_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.conversation_id} ({self.user_identifier})"


class ChatTurn(models.Model):
    ROLE_USER = "user"
    ROLE_BOT = "bot"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_BOT, "Bot"),
    ]

    conversation = models.ForeignKey(ChatConversation, related_name="turns", on_delete=models.CASCADE)
    role = models.CharField(max_length=8, choices=ROLE_CHOICES)
    message = models.TextField()
    intent = models.CharField(max_length=64, blank=True, default="")
    parameters = models.JSONField(default=dict, blank=True)
    service_now_action = models.CharField(max_length=128, blank=True, default="")
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.conversation_id} {self.role}: {self.message[:40]}"

    @property
    def conversation_id(self) -> str:
        return self.conversation.conversation_id
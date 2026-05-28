from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ChatConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("conversation_id", models.CharField(max_length=255, unique=True)),
                ("user_identifier", models.CharField(max_length=255)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ChatTurn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "User"), ("bot", "Bot")], max_length=8)),
                ("message", models.TextField()),
                ("intent", models.CharField(blank=True, default="", max_length=64)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("service_now_action", models.CharField(blank=True, default="", max_length=128)),
                ("success", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="turns", to="chat.chatconversation"),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]

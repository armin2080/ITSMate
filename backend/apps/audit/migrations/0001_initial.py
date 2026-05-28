from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("user_identifier", models.CharField(max_length=255)),
                ("original_message", models.TextField()),
                ("detected_intent", models.CharField(max_length=64)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("service_now_action", models.CharField(max_length=128)),
                ("success", models.BooleanField(default=False)),
                ("response_summary", models.TextField(blank=True, default="")),
                ("error_message", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
    ]

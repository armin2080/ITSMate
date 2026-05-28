from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_identifier", models.CharField(max_length=255, unique=True)),
                ("display_name", models.CharField(blank=True, default="", max_length=255)),
                ("servicenow_username", models.CharField(blank=True, default="", max_length=255)),
                ("preferences", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]

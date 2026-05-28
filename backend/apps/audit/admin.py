from django.contrib import admin

from .models import AuditLog, UserProfile


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user_identifier", "detected_intent", "service_now_action", "success")
    search_fields = ("user_identifier", "original_message", "detected_intent", "service_now_action")
    list_filter = ("success", "detected_intent", "service_now_action")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user_identifier", "display_name", "servicenow_username", "updated_at")
    search_fields = ("user_identifier", "display_name", "servicenow_username")

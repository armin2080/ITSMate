from django.contrib import admin

from .models import ChatConversation, ChatTurn


class ChatTurnInline(admin.TabularInline):
    model = ChatTurn
    extra = 0
    readonly_fields = ("role", "message", "intent", "parameters", "service_now_action", "success", "created_at")
    can_delete = False
    show_change_link = False


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ("conversation_id", "user_identifier", "title", "created_at", "updated_at")
    search_fields = ("conversation_id", "user_identifier", "title")
    inlines = [ChatTurnInline]


@admin.register(ChatTurn)
class ChatTurnAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "intent", "service_now_action", "success", "created_at")
    search_fields = ("conversation__conversation_id", "message", "intent", "service_now_action")
    list_filter = ("role", "success", "intent", "service_now_action")
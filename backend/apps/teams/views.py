from django.views.generic import TemplateView
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.chat.models import ChatConversation
from apps.chat.services import ChatOrchestrator


class TeamsChatTesterView(TemplateView):
    template_name = "teams/chat_tester.html"


class UserProfileSerializer(serializers.Serializer):
    user_identifier = serializers.CharField(max_length=255)
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    servicenow_username = serializers.CharField(max_length=255, required=False, allow_blank=True)


class TeamsUserProfileView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        audit_service = AuditService()
        profile = audit_service.update_profile(
            user_identifier=serializer.validated_data["user_identifier"],
            display_name=serializer.validated_data.get("display_name", ""),
            servicenow_username=serializer.validated_data.get("servicenow_username", ""),
        )
        return Response(
            {
                "user_identifier": profile.user_identifier,
                "display_name": profile.display_name,
                "servicenow_username": profile.servicenow_username,
                "updated_at": profile.updated_at,
            }
        )


class TeamsInsightsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user_identifier = request.query_params.get("user_id") or request.query_params.get("user_identifier") or "local-tester"
        audit_service = AuditService()
        return Response(audit_service.build_user_insights(user_identifier))


class TeamsChatHistoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        conversation_id = request.query_params.get("conversation_id")
        if not conversation_id:
            return Response({"detail": "conversation_id is required."}, status=400)

        conversation = ChatConversation.objects.filter(conversation_id=conversation_id).first()
        if not conversation:
            return Response({"conversation_id": conversation_id, "turns": []})

        turns = list(
            conversation.turns.order_by("created_at").values(
                "role",
                "message",
                "intent",
                "parameters",
                "service_now_action",
                "success",
                "created_at",
            )
        )
        return Response({"conversation_id": conversation_id, "turns": turns})


class TeamsWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        message = self._extract_text(payload, ("message",))
        if not message:
            message = self._extract_text(payload, ("text",))
        if not message:
            message = self._extract_text(payload, ("activity", "text"))
        if not message:
            message = self._extract_text(payload, ("body", "text"))
        if not message:
            return Response(
                {
                    "reply": "I did not receive a Teams message to process.",
                    "success": False,
                },
                status=400,
            )

        user_identifier = (
            payload.get("user_id")
            or self._extract_text(payload, ("from", "id"))
            or self._extract_text(payload, ("user", "id"))
            or self._extract_text(payload, ("from", "name"))
            or "unknown"
        )
        conversation_id = payload.get("conversation_id") or self._extract_text(payload, ("conversation", "id")) or payload.get("conversationId")

        orchestrator = ChatOrchestrator()
        result = orchestrator.handle_message(
            message=message,
            user_identifier=user_identifier,
            conversation_id=conversation_id,
        )
        return Response(
            {
                "reply": result.reply_text,
                "intent": result.intent,
                "parameters": result.parameters,
                "success": result.success,
                "needs_clarification": result.needs_clarification,
                "clarification_question": result.clarification_question,
            }
        )

    def _extract_text(self, payload: dict, path: tuple[str, ...]) -> str | None:
        current_value: object = payload
        for key in path:
            if not isinstance(current_value, dict):
                return None
            current_value = current_value.get(key)
        if current_value in {None, ""}:
            return None
        return str(current_value)

from __future__ import annotations

from django.db.models import Count

from .models import AuditLog, UserProfile
from .utils import compact_text


class AuditService:
    def record(
        self,
        *,
        user_identifier: str,
        original_message: str,
        detected_intent: str,
        parameters: dict,
        service_now_action: str,
        success: bool,
        response_summary: str = "",
        error_message: str = "",
    ) -> AuditLog:
        return AuditLog.objects.create(
            user_identifier=compact_text(user_identifier, 255),
            original_message=compact_text(original_message, 4000),
            detected_intent=compact_text(detected_intent, 64),
            parameters=parameters,
            service_now_action=compact_text(service_now_action, 128),
            success=success,
            response_summary=compact_text(response_summary, 4000),
            error_message=compact_text(error_message, 4000),
        )

    def get_or_create_profile(self, user_identifier: str) -> UserProfile:
        profile, _ = UserProfile.objects.get_or_create(user_identifier=compact_text(user_identifier, 255))
        return profile

    def update_profile(
        self,
        *,
        user_identifier: str,
        display_name: str | None = None,
        servicenow_username: str | None = None,
        preferences: dict | None = None,
    ) -> UserProfile:
        profile = self.get_or_create_profile(user_identifier)
        if display_name is not None:
            profile.display_name = compact_text(display_name, 255)
        if servicenow_username is not None:
            profile.servicenow_username = compact_text(servicenow_username, 255)
        if preferences is not None:
            profile.preferences = preferences
        profile.save()
        return profile

    def get_profile(self, user_identifier: str) -> UserProfile | None:
        return UserProfile.objects.filter(user_identifier=compact_text(user_identifier, 255)).first()

    def build_user_insights(self, user_identifier: str) -> dict:
        audits = AuditLog.objects.filter(user_identifier=compact_text(user_identifier, 255))
        total_actions = audits.count()
        successes = audits.filter(success=True).count()
        failures = audits.filter(success=False).count()
        recent_items = list(
            audits.values(
                "timestamp",
                "original_message",
                "detected_intent",
                "service_now_action",
                "success",
                "response_summary",
            )[:10]
        )
        intent_counts = list(
            audits.values("detected_intent").annotate(count=Count("id")).order_by("-count", "detected_intent")
        )
        profile = self.get_profile(user_identifier)
        return {
            "user_identifier": compact_text(user_identifier, 255),
            "profile": {
                "display_name": profile.display_name if profile else "",
                "servicenow_username": profile.servicenow_username if profile else "",
            },
            "summary": {
                "total_actions": total_actions,
                "successes": successes,
                "failures": failures,
                "success_rate": round((successes / total_actions) * 100, 1) if total_actions else 0.0,
            },
            "intent_counts": intent_counts,
            "recent_activity": recent_items,
        }

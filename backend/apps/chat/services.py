from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import re
from typing import Any
from datetime import date
import calendar

from django.conf import settings
from rest_framework.exceptions import ValidationError
from requests import RequestException

from apps.audit.services import AuditService
from apps.chat.models import ChatConversation, ChatTurn
from apps.llm.services import IntentParser
from apps.servicenow.client import ServiceNowClient


STATE_LABELS = {
    "1": "New",
    "2": "In Progress",
    "3": "On Hold",
    "6": "Resolved",
    "7": "Closed",
    "8": "Canceled",
}

INCIDENT_URL_TEMPLATE = "{instance_url}/nav_to.do?uri=incident.do?sys_id={sys_id}"


@dataclass
class ChatResult:
    reply_text: str
    intent: str
    parameters: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    needs_clarification: bool = False
    clarification_question: str = ""
    service_now_action: str = ""


class ChatOrchestrator:
    def __init__(
        self,
        intent_parser: IntentParser | None = None,
        service_now_client: ServiceNowClient | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.intent_parser = intent_parser or IntentParser()
        self.service_now_client = service_now_client or ServiceNowClient()
        self.audit_service = audit_service or AuditService()

    def handle_message(self, message: str, user_identifier: str, conversation_id: str | None = None) -> ChatResult:
        conversation = self._get_or_create_conversation(user_identifier=user_identifier, conversation_id=conversation_id)
        self._store_turn(conversation, role=ChatTurn.ROLE_USER, message=message)

        pending_action = self._get_pending_action(conversation)
        if pending_action:
            confirmation_result = self._handle_pending_action(message, user_identifier, conversation, pending_action)
            if confirmation_result is not None:
                return confirmation_result

        conversation_history = self._build_conversation_history(conversation)
        parsed_intent = self.intent_parser.parse(message, conversation_history=conversation_history)
        parsed_intent = self._apply_recent_incident_fallback(message, parsed_intent)
        parsed_intent = self._apply_sort_followup_fallback(message, conversation, parsed_intent)
        # Map natural language month/year phrases (e.g. "March 2024") to explicit
        # created_from / created_to date filters so we don't fully rely on the LLM.
        parsed_intent = self._apply_natural_date_range_mapping(message, parsed_intent)

        if parsed_intent.intent == "clarify":
            fallback_search = self._build_personal_incident_search(message)
            if fallback_search is not None:
                parsed_intent = type(parsed_intent)(
                    intent="search_incidents",
                    parameters=fallback_search,
                    clarification_question="",
                )

        if parsed_intent.intent == "clarify":
            reply_text = parsed_intent.clarification_question
            self._store_turn(conversation, role=ChatTurn.ROLE_BOT, message=reply_text, intent=parsed_intent.intent, parameters={}, service_now_action="clarification_requested", success=False)
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent=parsed_intent.intent,
                parameters={},
                service_now_action="clarification_requested",
                success=False,
                response_summary=reply_text,
            )
            return ChatResult(
                reply_text=reply_text,
                intent=parsed_intent.intent,
                parameters={},
                success=False,
                needs_clarification=True,
                clarification_question=reply_text,
                service_now_action="clarification_requested",
            )

        try:
            if parsed_intent.intent == "search_incidents":
                records = self.service_now_client.search_incidents(parsed_intent.parameters)
                reply_text = self._format_search_results(records, parsed_intent.parameters)
                service_now_action = "search_incidents"
                parameters = parsed_intent.parameters
            elif parsed_intent.intent == "get_incident_by_number":
                number = parsed_intent.parameters.get("number")
                if not number:
                    raise ValidationError({"number": "Incident number is required."})
                record = self.service_now_client.get_incident_by_number(number)
                records = [record] if record else []
                reply_text = self._format_single_incident(record, number)
                service_now_action = "get_incident_by_number"
                parameters = {"number": number}
            elif parsed_intent.intent == "summarize_incident":
                number = parsed_intent.parameters.get("number")
                if not number:
                    raise ValidationError({"number": "Incident number is required for summarization."})
                record = self.service_now_client.get_incident_by_number(number)
                records = [record] if record else []
                reply_text = self._format_incident_summary(record, number)
                service_now_action = "summarize_incident"
                parameters = {"number": number}
            elif parsed_intent.intent == "update_incident":
                number = str(parsed_intent.parameters.get("number") or "").strip()
                if not number:
                    raise ValidationError({"number": "Incident number is required."})
                update_fields = self._extract_update_fields(parsed_intent.parameters)
                if not update_fields:
                    raise ValidationError({"updates": "Provide at least one field to update."})
                parameters = {"number": number, **update_fields}
                reply_text = self._format_update_confirmation(number, update_fields)
                self._set_pending_action(
                    conversation,
                    action="update_incident",
                    parameters=parameters,
                    message=reply_text,
                )
                service_now_action = "update_incident_confirmation_requested"
            elif parsed_intent.intent == "count_incidents":
                parameters = self._normalize_count_parameters(parsed_intent.parameters, user_identifier=user_identifier)
                count = self.service_now_client.count_incidents(parameters)
                reply_text = self._format_count_result(count, parameters)
                service_now_action = "count_incidents"
            else:
                raise ValidationError({"intent": f"Unsupported intent: {parsed_intent.intent}"})
        except ValidationError as exc:
            reply_text = self._format_validation_error(exc)
            self._store_turn(conversation, role=ChatTurn.ROLE_BOT, message=reply_text, intent=parsed_intent.intent, parameters=parsed_intent.parameters, service_now_action="validation_failed", success=False)
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent=parsed_intent.intent,
                parameters=parsed_intent.parameters,
                service_now_action="validation_failed",
                success=False,
                response_summary=reply_text,
                error_message=str(exc),
            )
            return ChatResult(
                reply_text=reply_text,
                intent=parsed_intent.intent,
                parameters=parsed_intent.parameters,
                success=False,
                service_now_action="validation_failed",
            )
        except RequestException as exc:
            reply_text = "I could not reach ServiceNow right now. Please try again shortly."
            self._store_turn(conversation, role=ChatTurn.ROLE_BOT, message=reply_text, intent=parsed_intent.intent, parameters=parsed_intent.parameters, service_now_action="servicenow_request_failed", success=False)
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent=parsed_intent.intent,
                parameters=parsed_intent.parameters,
                service_now_action="servicenow_request_failed",
                success=False,
                response_summary=reply_text,
                error_message=str(exc),
            )
            return ChatResult(
                reply_text=reply_text,
                intent=parsed_intent.intent,
                parameters=parsed_intent.parameters,
                success=False,
                service_now_action="servicenow_request_failed",
            )

        self.audit_service.record(
            user_identifier=user_identifier,
            original_message=message,
            detected_intent=parsed_intent.intent,
            parameters=parameters,
            service_now_action=service_now_action,
            success=service_now_action != "update_incident_confirmation_requested",
            response_summary=reply_text,
        )
        self._store_turn(
            conversation,
            role=ChatTurn.ROLE_BOT,
            message=reply_text,
            intent=parsed_intent.intent,
            parameters=parameters,
            service_now_action=service_now_action,
            success=service_now_action != "update_incident_confirmation_requested",
        )
        return ChatResult(
            reply_text=reply_text,
            intent=parsed_intent.intent,
            parameters=parameters,
            success=service_now_action != "update_incident_confirmation_requested",
            service_now_action=service_now_action,
        )

    def _format_search_results(self, records: list[dict[str, Any]], parameters: dict[str, Any]) -> str:
        if not records:
            return "No incidents matched your search."

        lines = [f"Found {len(records)} incident(s).", "", self._incident_table_header(parameters), self._incident_table_separator(parameters)]
        for record in records[:20]:
            lines.append(self._format_record_row(record, parameters))
        if len(records) > 20:
            lines.append("")
            lines.append(f"Showing the first 20 of {len(records)} incidents.")
        if parameters.get("created_today"):
            lines.append("Filtered to incidents created today.")
        if parameters.get("created_last_days"):
            lines.append(f"Filtered to incidents created in the last {parameters['created_last_days']} day(s).")
        if self._should_include_created_on(parameters):
            lines.append("Sorted by created date, newest first.")
        return "\n".join(lines)

    def _format_single_incident(self, record: dict[str, Any] | None, number: str) -> str:
        if not record:
            return f"I could not find incident {number}."
        return "\n".join([
            f"Incident {record.get('number', number)}",
            f"State: {self._human_state(record.get('state'))}",
            f"Priority: {record.get('priority', 'Unknown')}",
            f"Assignment group: {self._human_value(record.get('assignment_group'))}",
            f"Assigned to: {self._human_value(record.get('assigned_to'))}",
            f"Short description: {self._human_value(record.get('short_description'))}",
            "",
            self._format_extra_incident_fields(record),
        ])

    def _format_incident_summary(self, record: dict[str, Any] | None, number: str) -> str:
        if not record:
            return f"I could not find incident {number} to summarize."
        notes = self._fetch_notes(record)
        return "\n".join([
            f"Summary for {record.get('number', number)}",
            f"Short description: {self._human_value(record.get('short_description'))}",
            f"Current state: {self._human_state(record.get('state'))}",
            f"Priority: {record.get('priority', 'Unknown')}",
            f"Assignment group: {self._human_value(record.get('assignment_group'))}",
            f"Assigned to: {self._human_value(record.get('assigned_to'))}",
            f"Opened by: {self._human_value(record.get('opened_by'))}",
            f"Created: {self._human_value(record.get('sys_created_on'))}",
            f"Description: {self._human_value(record.get('description'))}",
            "",
            self._format_notes_block(notes),
            "",
            self._format_extra_incident_fields(record),
        ])

    def _fetch_notes(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        sys_id = str(record.get("sys_id") or "").strip()
        if not sys_id:
            return []
        try:
            return self.service_now_client.get_incident_notes(sys_id)
        except RequestException:
            return []

    def _format_notes_block(self, notes: list[dict[str, Any]]) -> str:
        if not notes:
            return "Notes: No comments or work notes were returned from ServiceNow."

        lines = ["Notes:"]
        for note in notes[:8]:
            note_type = self._human_value(note.get("element"))
            created_by = self._human_value(note.get("sys_created_by"))
            created_on = self._human_value(note.get("sys_created_on"))
            value = self._human_value(note.get("value"))
            lines.append(f"- [{note_type}] {created_on} by {created_by}: {value}")
        if len(notes) > 8:
            lines.append(f"- Showing the latest 8 of {len(notes)} notes.")
        return "\n".join(lines)

    def _format_extra_incident_fields(self, record: dict[str, Any]) -> str:
        excluded_keys = {
            "sys_id",
            "number",
            "state",
            "priority",
            "short_description",
            "assignment_group",
            "assigned_to",
            "opened_by",
            "sys_created_on",
            "description",
            "active",
        }
        extra_lines: list[str] = []
        for key in sorted(record.keys()):
            if key in excluded_keys or key.startswith("_"):
                continue
            value = record.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, tuple, set, dict)) and not value:
                continue
            extra_lines.append(f"- {self._human_field_label(key)}: {self._human_value(value)}")
        if not extra_lines:
            return "Additional fields: None returned."
        return "\n".join(["Additional fields:", *extra_lines])

    def _human_field_label(self, value: str) -> str:
        return value.replace("_", " ").strip().title()

    def _incident_table_header(self, parameters: dict[str, Any]) -> str:
        if self._should_include_created_on(parameters):
            return "| Incident | Created | State | Priority | Assignee | Short description |"
        return "| Incident | State | Priority | Assignee | Short description |"

    def _incident_table_separator(self, parameters: dict[str, Any]) -> str:
        if self._should_include_created_on(parameters):
            return "| --- | --- | --- | --- | --- | --- |"
        return "| --- | --- | --- | --- | --- |"

    def _format_record_row(self, record: dict[str, Any], parameters: dict[str, Any]) -> str:
        number = self._human_value(record.get('number'))
        incident_link = self._incident_link(record)
        short_description = self._human_value(record.get('short_description'))
        created_on = self._human_value(record.get('sys_created_on'))
        if self._should_include_created_on(parameters):
            return (
                f"| [{number}]({incident_link}) | "
                f"{created_on} | "
                f"{self._human_state(record.get('state'))} | "
                f"P{self._human_value(record.get('priority'))} | "
                f"{self._human_value(record.get('assigned_to'))} | "
                f"{short_description} |"
            )
        return (
            f"| [{number}]({incident_link}) | "
            f"{self._human_state(record.get('state'))} | "
            f"P{self._human_value(record.get('priority'))} | "
            f"{self._human_value(record.get('assigned_to'))} | "
            f"{short_description} |"
        )

    def _format_count_result(self, count: int, parameters: dict[str, Any]) -> str:
        if parameters.get("opened_by_me"):
            scope = "opened by you"
        elif parameters.get("opened_by"):
            scope = f"opened by {parameters['opened_by']}"
        elif parameters.get("assigned_to"):
            scope = f"assigned to {parameters['assigned_to']}"
        elif parameters.get("assignment_group"):
            scope = f"assigned to {parameters['assignment_group']}"
        else:
            scope = "matching your filter"

        time_window = ""
        if parameters.get("created_today"):
            time_window = " today"
        elif parameters.get("created_last_days"):
            days = parameters["created_last_days"]
            time_window = f" in the last {days} day(s)"

        return f"There are {count} incident(s) {scope}{time_window}."

    def _normalize_count_parameters(self, parameters: dict[str, Any], user_identifier: str) -> dict[str, Any]:
        normalized = dict(parameters)
        if normalized.get("opened_by_me"):
            profile = self.audit_service.get_profile(user_identifier)
            if profile and profile.servicenow_username:
                normalized.pop("opened_by_me", None)
                normalized["opened_by"] = profile.servicenow_username
        return normalized

    def _build_personal_incident_search(self, message: str) -> dict[str, Any] | None:
        normalized_message = " ".join(message.lower().split())
        if "incident" not in normalized_message and "incidents" not in normalized_message:
            return None
        if not re.search(r"\b(my|mine)\b", normalized_message):
            return None

        parameters: dict[str, Any] = {"opened_by_me": True}
        if re.search(r"\bopen\b|\bactive\b", normalized_message):
            parameters["state"] = "open"
        elif "closed" in normalized_message:
            parameters["state"] = "closed"
        elif "resolved" in normalized_message:
            parameters["state"] = "resolved"

        if "today" in normalized_message:
            parameters["created_today"] = True
        elif "last week" in normalized_message or "last 7 days" in normalized_message or "last seven days" in normalized_message:
            parameters["created_last_days"] = 7

        return parameters

    def _apply_recent_incident_fallback(self, message: str, parsed_intent: ParsedIntent) -> ParsedIntent:
        recent_search = self._build_recent_incidents_search(message)
        if recent_search is None:
            return parsed_intent

        if parsed_intent.intent in {"clarify", "search_incidents"}:
            merged_parameters = dict(parsed_intent.parameters)
            merged_parameters.update(recent_search)
            merged_parameters.pop("created_today", None)
            merged_parameters.pop("created_last_days", None)
            return type(parsed_intent)(intent="search_incidents", parameters=merged_parameters, clarification_question="")

        return parsed_intent

    def _apply_sort_followup_fallback(self, message: str, conversation: ChatConversation, parsed_intent: ParsedIntent) -> ParsedIntent:
        if not self._looks_like_sort_followup(message):
            return parsed_intent

        previous_search = self._get_last_search_parameters(conversation)
        if not previous_search:
            return parsed_intent

        merged_parameters = dict(previous_search)
        merged_parameters["order_by_desc"] = "sys_created_on"
        merged_parameters["include_created_on"] = True

        if parsed_intent.intent == "clarify":
            return type(parsed_intent)(intent="search_incidents", parameters=merged_parameters, clarification_question="")

        if parsed_intent.intent == "search_incidents":
            merged_parameters.update(parsed_intent.parameters)
            return type(parsed_intent)(intent="search_incidents", parameters=merged_parameters, clarification_question="")

        return parsed_intent

    def _looks_like_sort_followup(self, message: str) -> bool:
        normalized_message = " ".join(message.lower().split())
        if not any(token in normalized_message for token in ("sort", "sorted", "order", "ordered", "arrange", "ascending", "descending")):
            return False
        return "created" in normalized_message or "date" in normalized_message or "newest" in normalized_message or "oldest" in normalized_message

    def _get_last_search_parameters(self, conversation: ChatConversation) -> dict[str, Any] | None:
        previous_turn = (
            conversation.turns.filter(role=ChatTurn.ROLE_BOT, intent="search_incidents", success=True)
            .order_by("-created_at")
            .first()
        )
        if not previous_turn:
            return None
        parameters = previous_turn.parameters if isinstance(previous_turn.parameters, dict) else {}
        return dict(parameters)

    def _build_recent_incidents_search(self, message: str) -> dict[str, Any] | None:
        normalized_message = " ".join(message.lower().split())
        if "incident" not in normalized_message and "incidents" not in normalized_message:
            return None

        recent_match = re.search(
            r"\b(?:last|latest|most recent|newest)\s+(\d+)\s+incidents?\b",
            normalized_message,
        )
        if not recent_match:
            return None

        limit = int(recent_match.group(1))
        return {
            "limit": limit,
            "order_by_desc": "sys_created_on",
            "include_created_on": True,
        }

    def _apply_natural_date_range_mapping(self, message: str, parsed_intent: ParsedIntent) -> ParsedIntent:
        """If the user mentioned a month/year (e.g. 'March 2024'), add created_from/created_to
        to the parsed_intent.parameters unless those keys already exist.
        """
        if not parsed_intent or parsed_intent.intent not in {"search_incidents", "count_incidents"}:
            return parsed_intent

        parameters = dict(parsed_intent.parameters or {})
        # don't override explicit LLM-provided dates
        if parameters.get("created_from") or parameters.get("created_to"):
            return parsed_intent

        found = self._extract_month_year(message)
        if not found:
            return parsed_intent

        month, year = found
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        parameters.setdefault("created_from", first_day)
        parameters.setdefault("created_to", last_day)

        return type(parsed_intent)(intent=parsed_intent.intent, parameters=parameters, clarification_question=parsed_intent.clarification_question)

    def _extract_month_year(self, text: str) -> tuple[int, int] | None:
        """Return (month, year) if a month + year is found in the text, else None.

        Recognises full and short month names (case-insensitive), e.g. 'March 2024', 'Mar 2024'.
        """
        normalized = text.strip()
        if not normalized:
            return None
        # match e.g. "march 2024" or "mar 2024"
        pattern = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(20\d{2}|19\d{2})\b", re.IGNORECASE)
        m = pattern.search(normalized)
        if not m:
            return None
        month_str = m.group(1).lower()
        year = int(m.group(2))
        month_map = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        month = month_map.get(month_str)
        if not month:
            return None
        return (month, year)

    def _should_include_created_on(self, parameters: dict[str, Any]) -> bool:
        return bool(parameters.get("include_created_on") or parameters.get("limit") or parameters.get("order_by_desc"))

    def _get_or_create_conversation(self, user_identifier: str, conversation_id: str | None) -> ChatConversation:
        stable_conversation_id = conversation_id or f"{user_identifier}-default"
        conversation, _ = ChatConversation.objects.get_or_create(
            conversation_id=stable_conversation_id,
            defaults={"user_identifier": user_identifier},
        )
        if conversation.user_identifier != user_identifier:
            conversation.user_identifier = user_identifier
            conversation.save(update_fields=["user_identifier", "updated_at"])
        return conversation

    def _build_conversation_history(self, conversation: ChatConversation, turn_limit: int = 8) -> str:
        recent_turns = list(conversation.turns.order_by("-created_at")[:turn_limit])
        recent_turns.reverse()
        if not recent_turns:
            return "No prior messages."
        lines: list[str] = []
        for turn in recent_turns:
            role_label = "User" if turn.role == ChatTurn.ROLE_USER else "Bot"
            content = " ".join(turn.message.split())
            if turn.role == ChatTurn.ROLE_BOT and turn.intent:
                lines.append(f"{role_label} ({turn.intent}): {content}")
            else:
                lines.append(f"{role_label}: {content}")
        return "\n".join(lines)

    def _store_turn(
        self,
        conversation: ChatConversation,
        *,
        role: str,
        message: str,
        intent: str = "",
        parameters: dict[str, Any] | None = None,
        service_now_action: str = "",
        success: bool = True,
    ) -> None:
        ChatTurn.objects.create(
            conversation=conversation,
            role=role,
            message=message,
            intent=intent,
            parameters=parameters or {},
            service_now_action=service_now_action,
            success=success,
        )

    def _incident_link(self, record: dict[str, Any]) -> str:
        sys_id = str(record.get("sys_id") or "").strip()
        if not sys_id:
            return settings.SERVICENOW_INSTANCE_URL.rstrip("/")
        return INCIDENT_URL_TEMPLATE.format(instance_url=settings.SERVICENOW_INSTANCE_URL.rstrip("/"), sys_id=sys_id)

    def _human_state(self, value: Any) -> str:
        if value is None:
            return "Unknown"
        return STATE_LABELS.get(str(value), str(value))

    def _human_value(self, value: Any) -> str:
        if isinstance(value, dict):
            return value.get("display_value") or value.get("value") or "Unknown"
        if value in {None, ""}:
            return "Unknown"
        return str(value)

    def _format_validation_error(self, exc: ValidationError) -> str:
        return f"I need a valid incident filter before I can continue: {exc.detail}"

    def _format_update_confirmation(self, number: str, update_fields: dict[str, Any]) -> str:
        details = ", ".join(f"{key}={self._human_value(value)}" for key, value in sorted(update_fields.items()))
        return f"I’m ready to update incident {number} with {details}. Reply 'yes' to confirm or 'cancel' to stop."

    def _get_pending_action(self, conversation: ChatConversation) -> dict[str, Any] | None:
        action = str(getattr(conversation, "pending_service_now_action", "") or "").strip()
        parameters = getattr(conversation, "pending_service_now_parameters", {})
        if not action or not isinstance(parameters, dict):
            return None
        return {"action": action, "parameters": dict(parameters)}

    def _set_pending_action(self, conversation: ChatConversation, *, action: str, parameters: dict[str, Any], message: str) -> None:
        conversation.pending_service_now_action = action
        conversation.pending_service_now_parameters = parameters
        conversation.pending_service_now_message = message
        conversation.save(update_fields=["pending_service_now_action", "pending_service_now_parameters", "pending_service_now_message", "updated_at"])

    def _clear_pending_action(self, conversation: ChatConversation) -> None:
        conversation.pending_service_now_action = ""
        conversation.pending_service_now_parameters = {}
        conversation.pending_service_now_message = ""
        conversation.save(update_fields=["pending_service_now_action", "pending_service_now_parameters", "pending_service_now_message", "updated_at"])

    def _handle_pending_action(
        self,
        message: str,
        user_identifier: str,
        conversation: ChatConversation,
        pending_action: dict[str, Any],
    ) -> ChatResult | None:
        normalized_message = " ".join(message.lower().split())
        pending_parameters = dict(pending_action.get("parameters", {}))

        if self._is_cancel_message(normalized_message):
            self._clear_pending_action(conversation)
            reply_text = "Canceled the pending update."
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_canceled",
                success=False,
                response_summary=reply_text,
            )
            self._store_turn(
                conversation,
                role=ChatTurn.ROLE_BOT,
                message=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_canceled",
                success=False,
            )
            return ChatResult(
                reply_text=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                success=False,
                service_now_action="update_incident_canceled",
            )

        if not self._is_confirmation_message(normalized_message):
            reply_text = str(getattr(conversation, "pending_service_now_message", "") or "Reply 'yes' to confirm or 'cancel' to stop.")
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_confirmation_requested",
                success=False,
                response_summary=reply_text,
            )
            self._store_turn(
                conversation,
                role=ChatTurn.ROLE_BOT,
                message=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_confirmation_requested",
                success=False,
            )
            return ChatResult(
                reply_text=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                success=False,
                needs_clarification=True,
                clarification_question=reply_text,
                service_now_action="update_incident_confirmation_requested",
            )

        number = str(pending_parameters.get("number") or "").strip()
        update_fields = {key: value for key, value in pending_parameters.items() if key != "number"}
        record = self.service_now_client.get_incident_by_number(number)
        if not record:
            self._clear_pending_action(conversation)
            reply_text = f"I could not find incident {number} to update."
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_not_found",
                success=False,
                response_summary=reply_text,
            )
            self._store_turn(
                conversation,
                role=ChatTurn.ROLE_BOT,
                message=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_not_found",
                success=False,
            )
            return ChatResult(
                reply_text=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                success=False,
                service_now_action="update_incident_not_found",
            )

        updated = self.service_now_client.update_incident(str(record.get("sys_id") or "").strip(), update_fields)
        self._clear_pending_action(conversation)
        if not updated:
            reply_text = f"I could not update incident {number}."
            self.audit_service.record(
                user_identifier=user_identifier,
                original_message=message,
                detected_intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_failed",
                success=False,
                response_summary=reply_text,
            )
            self._store_turn(
                conversation,
                role=ChatTurn.ROLE_BOT,
                message=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                service_now_action="update_incident_failed",
                success=False,
            )
            return ChatResult(
                reply_text=reply_text,
                intent="update_incident",
                parameters=pending_parameters,
                success=False,
                service_now_action="update_incident_failed",
            )

        reply_text = self._format_update_result(number, updated, update_fields)
        self.audit_service.record(
            user_identifier=user_identifier,
            original_message=message,
            detected_intent="update_incident",
            parameters=pending_parameters,
            service_now_action="update_incident",
            success=True,
            response_summary=reply_text,
        )
        self._store_turn(
            conversation,
            role=ChatTurn.ROLE_BOT,
            message=reply_text,
            intent="update_incident",
            parameters=pending_parameters,
            service_now_action="update_incident",
            success=True,
        )
        return ChatResult(
            reply_text=reply_text,
            intent="update_incident",
            parameters=pending_parameters,
            success=True,
            service_now_action="update_incident",
        )

    def _is_confirmation_message(self, message: str) -> bool:
        return message in {"yes", "y", "confirm", "confirmed", "do it", "proceed", "apply"}

    def _is_cancel_message(self, message: str) -> bool:
        return message in {"cancel", "stop", "abort", "never mind", "nevermind"}

    def _format_update_result(self, number: str, updated_record: dict[str, Any], update_fields: dict[str, Any]) -> str:
        changes = ", ".join(sorted(update_fields.keys()))
        state = self._human_state(updated_record.get("state"))
        return f"Updated incident {number}: {changes}. Current state: {state}."

    def _extract_update_fields(self, parameters: dict[str, Any]) -> dict[str, Any]:
        allowed = {"state", "priority", "assignment_group", "assigned_to", "comment", "work_notes"}
        update_fields: dict[str, Any] = {}
        for key in allowed:
            value = parameters.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            update_fields[key] = value
        return update_fields

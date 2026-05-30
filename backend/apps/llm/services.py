from __future__ import annotations

from dataclasses import dataclass
import json
import re

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .prompts import INTENT_EXTRACTION_PROMPT
from .providers import GroqLLMProvider
from .serializers import IntentParseSerializer


GROUP_HINT_WORDS = {
    "team",
    "group",
    "support",
    "ops",
    "operations",
    "it",
    "helpdesk",
    "service",
    "desk",
    "infra",
    "infrastructure",
}

PERSON_NAME_PATTERN = re.compile(r"^[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,2}$")


@dataclass
class ParsedIntent:
    intent: str
    parameters: dict
    clarification_question: str = ""


class IntentParser:
    def __init__(self, provider=None) -> None:
        self.provider = provider or GroqLLMProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        )

    def parse(self, message: str, conversation_history: str = "") -> ParsedIntent:
        prompt = INTENT_EXTRACTION_PROMPT.format(
            message=message.strip(),
            conversation_history=conversation_history.strip(),
        )
        raw_response = self.provider.generate_json(prompt)
        try:
            parsed_payload = json.loads(raw_response)
        except json.JSONDecodeError:
            return ParsedIntent(
                intent="clarify",
                parameters={},
                clarification_question="I could not interpret that request. Which incident filter should I use?",
            )

        serializer = IntentParseSerializer(data=parsed_payload)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            return ParsedIntent(
                intent="clarify",
                parameters={},
                clarification_question="I need a clearer incident request. Please provide a number, keyword, state, priority, or assignment group.",
            )

        validated = serializer.validated_data
        intent = validated["intent"]
        parameters = self._normalize_parameters(validated.get("parameters", {}) or {})
        clarification_question = validated.get("clarification_question", "") or ""

        if intent == "clarify":
            clarification_question = clarification_question or (
                "I need one more detail to continue. Do you want me to search by number, state, priority, assignment group, assignee, keyword, or created today?"
            )
            return ParsedIntent(intent=intent, parameters={}, clarification_question=clarification_question)

        return ParsedIntent(
            intent=intent,
            parameters=parameters,
            clarification_question=clarification_question,
        )

    def _normalize_parameters(self, parameters: dict) -> dict:
        normalized: dict = {}
        for key, value in parameters.items():
            if value is None:
                continue
            if isinstance(value, str):
                stripped_value = value.strip()
                if not stripped_value:
                    continue
                normalized[key] = stripped_value
                continue
            normalized[key] = value
        assignment_group = normalized.get("assignment_group")
        assigned_to = normalized.get("assigned_to")
        if assignment_group and not assigned_to and self._looks_like_person_name(assignment_group):
            normalized["assigned_to"] = assignment_group
            normalized.pop("assignment_group", None)
        return normalized

    def _looks_like_person_name(self, value: object) -> bool:
        if not isinstance(value, str):
            return False
        stripped = " ".join(value.split())
        if not stripped:
            return False
        if not PERSON_NAME_PATTERN.match(stripped):
            return False
        lowered_tokens = {token.lower() for token in stripped.split()}
        return lowered_tokens.isdisjoint(GROUP_HINT_WORDS)

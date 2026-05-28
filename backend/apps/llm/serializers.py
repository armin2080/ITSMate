from rest_framework import serializers


class IntentParseSerializer(serializers.Serializer):
    intent = serializers.ChoiceField(
        choices=[
            ("search_incidents", "search_incidents"),
            ("count_incidents", "count_incidents"),
            ("get_incident_by_number", "get_incident_by_number"),
            ("summarize_incident", "summarize_incident"),
            ("clarify", "clarify"),
        ]
    )
    parameters = serializers.DictField(required=False, default=dict)
    clarification_question = serializers.CharField(required=False, allow_blank=True, default="")

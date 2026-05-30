from rest_framework import serializers


class IncidentSearchFiltersSerializer(serializers.Serializer):
    number = serializers.CharField(required=False, allow_blank=True, max_length=50)
    state = serializers.CharField(required=False, allow_blank=True, max_length=32)
    priority = serializers.CharField(required=False, allow_blank=True, max_length=16)
    assignment_group = serializers.CharField(required=False, allow_blank=True, max_length=120)
    assigned_to = serializers.CharField(required=False, allow_blank=True, max_length=120)
    opened_by = serializers.CharField(required=False, allow_blank=True, max_length=120)
    opened_by_me = serializers.BooleanField(required=False, default=False)
    keyword = serializers.CharField(required=False, allow_blank=True, max_length=255)
    created_today = serializers.BooleanField(required=False, default=False)
    created_last_days = serializers.IntegerField(required=False, min_value=1, max_value=365)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)


class IncidentNumberSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=50)

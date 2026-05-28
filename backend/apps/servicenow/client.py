from __future__ import annotations

import requests
from django.conf import settings

from .query_builder import IncidentQueryBuilder
from .serializers import IncidentNumberSerializer, IncidentSearchFiltersSerializer


class ServiceNowClient:
    def __init__(
        self,
        instance_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.instance_url = (instance_url or settings.SERVICENOW_INSTANCE_URL).rstrip("/")
        self.username = username if username is not None else settings.SERVICENOW_USERNAME
        self.password = password if password is not None else settings.SERVICENOW_PASSWORD
        self.timeout = timeout if timeout is not None else settings.SERVICENOW_TIMEOUT_SECONDS
        self.session = requests.Session()
        self.session.auth = (self.username, self.password)
        self.session.headers.update({"Accept": "application/json"})
        self.query_builder = IncidentQueryBuilder()

    def search_incidents(self, filters: dict) -> list[dict]:
        serializer = IncidentSearchFiltersSerializer(data=filters)
        serializer.is_valid(raise_exception=True)
        sysparm_query = self.query_builder.build(serializer.validated_data)
        response = self.session.get(
            f"{self.instance_url}/api/now/table/incident",
            params={
                "sysparm_query": sysparm_query,
                "sysparm_limit": settings.SERVICENOW_MAX_RESULTS,
                "sysparm_display_value": "true",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json().get("result", [])

    def count_incidents(self, filters: dict) -> int:
        serializer = IncidentSearchFiltersSerializer(data=filters)
        serializer.is_valid(raise_exception=True)
        sysparm_query = self.query_builder.build(serializer.validated_data)
        response = self.session.get(
            f"{self.instance_url}/api/now/stats/incident",
            params={
                "sysparm_count": "true",
                "sysparm_query": sysparm_query,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return int(payload.get("result", {}).get("stats", {}).get("count", 0))

    def get_incident_by_number(self, number: str) -> dict | None:
        serializer = IncidentNumberSerializer(data={"number": number})
        serializer.is_valid(raise_exception=True)
        sysparm_query = self.query_builder.build({"number": serializer.validated_data["number"]})
        response = self.session.get(
            f"{self.instance_url}/api/now/table/incident",
            params={
                "sysparm_query": sysparm_query,
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        return results[0] if results else None

    def get_incident_notes(self, sys_id: str, limit: int = 10) -> list[dict]:
        response = self.session.get(
            f"{self.instance_url}/api/now/table/sys_journal_field",
            params={
                "sysparm_query": f"name=incident^element_id={sys_id}^elementINcomments,work_notes",
                "sysparm_limit": limit,
                "sysparm_fields": "sys_created_on,sys_created_by,element,value",
                "sysparm_display_value": "true",
                "sysparm_order_by_desc": "sys_created_on",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        return list(reversed(results))

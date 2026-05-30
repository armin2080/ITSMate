from __future__ import annotations

from datetime import datetime
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
        search_filters = dict(filters)
        limit = search_filters.pop("limit", None)
        order_by_desc = search_filters.pop("order_by_desc", None)
        search_filters = {
            key: value
            for key, value in search_filters.items()
            if value is not None and not (isinstance(value, str) and not value.strip())
        }
        serializer = IncidentSearchFiltersSerializer(data=search_filters)
        serializer.is_valid(raise_exception=True)
        sysparm_query = self.query_builder.build(serializer.validated_data)
        requested_limit = int(limit) if limit else None
        candidate_limit = requested_limit or settings.SERVICENOW_MAX_RESULTS
        if order_by_desc and requested_limit:
            candidate_limit = max(requested_limit * 5, settings.SERVICENOW_MAX_RESULTS)
        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": candidate_limit,
            "sysparm_display_value": "true",
        }
        if order_by_desc:
            params["sysparm_order_by_desc"] = order_by_desc
        response = self.session.get(
            f"{self.instance_url}/api/now/table/incident",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("result", [])
        results = self._sort_incidents(results, order_by_desc=order_by_desc)
        if requested_limit is not None:
            return results[:requested_limit]
        return results

    def count_incidents(self, filters: dict) -> int:
        normalized_filters = {
            key: value
            for key, value in dict(filters).items()
            if value is not None and not (isinstance(value, str) and not value.strip())
        }
        serializer = IncidentSearchFiltersSerializer(data=normalized_filters)
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

    def _sort_incidents(self, results: list[dict], order_by_desc: str | None = None) -> list[dict]:
        if not results or not order_by_desc:
            return results

        sort_key = order_by_desc.strip()
        if not sort_key:
            return results

        reverse = True

        def sort_value(record: dict) -> datetime:
            value = record.get(sort_key)
            if not isinstance(value, str):
                return datetime.min
            try:
                return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return datetime.min

        return sorted(results, key=sort_value, reverse=reverse)

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

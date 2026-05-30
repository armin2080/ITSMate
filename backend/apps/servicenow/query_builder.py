from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone
from datetime import date


def _sanitize_query_value(value: str) -> str:
    return " ".join(str(value).replace("^", " ").replace("=", " ").replace("@", " ").split())


@dataclass(frozen=True)
class IncidentQueryBuilder:
    def build(self, filters: dict) -> str:
        fragments: list[str] = []

        number = filters.get("number")
        if number:
            fragments.append(f"number={_sanitize_query_value(number)}")

        state = filters.get("state")
        if state:
            fragments.extend(self._build_state_fragment(state))

        priority = filters.get("priority")
        if priority:
            fragments.append(f"priority={_sanitize_query_value(priority)}")

        assignment_group = filters.get("assignment_group")
        if assignment_group:
            fragments.append(f"assignment_groupLIKE{_sanitize_query_value(assignment_group)}")

        assigned_to = filters.get("assigned_to")
        if assigned_to:
            fragments.append(f"assigned_toLIKE{_sanitize_query_value(assigned_to)}")

        opened_by = filters.get("opened_by")
        if opened_by:
            fragments.append(f"opened_byLIKE{_sanitize_query_value(opened_by)}")

        if filters.get("opened_by_me"):
            fragments.append("opened_byDYNAMIC90d1921e5f510100a9ad2572f2b477fe")

        keyword = filters.get("keyword")
        if keyword:
            fragments.append(f"short_descriptionLIKE{_sanitize_query_value(keyword)}")

        if filters.get("created_today"):
            fragments.append("sys_created_onONToday@javascript:gs.beginningOfToday()@javascript:gs.endOfToday()")

        created_last_days = filters.get("created_last_days")
        if created_last_days:
            fragments.append(
                f"sys_created_on>=javascript:gs.daysAgoStart({int(created_last_days)})"
            )

        created_from = filters.get("created_from")
        if created_from:
            # created_from is a date object (YYYY-MM-DD); include from start of day
            if isinstance(created_from, date):
                date_str = created_from.strftime("%Y-%m-%d")
            else:
                date_str = str(created_from)
            fragments.append(f"sys_created_on>=javascript:gs.dateGenerate('{date_str} 00:00:00')")

        created_to = filters.get("created_to")
        if created_to:
            # created_to is a date object (YYYY-MM-DD); include through end of day
            if isinstance(created_to, date):
                date_str = created_to.strftime("%Y-%m-%d")
            else:
                date_str = str(created_to)
            fragments.append(f"sys_created_on<=javascript:gs.dateGenerate('{date_str} 23:59:59')")

        if not fragments:
            return "active=true"

        return "^".join(fragments)

    def _build_state_fragment(self, state: str) -> list[str]:
        normalized_state = str(state).strip().lower()
        if normalized_state in {"open", "active"}:
            return ["active=true"]
        if normalized_state in {"closed"}:
            return ["active=false", "stateIN6,7,8"]
        if normalized_state in {"resolved"}:
            return ["stateIN6"]
        if normalized_state in {"new"}:
            return ["state=1"]
        if normalized_state in {"in_progress", "in progress", "progress"}:
            return ["state=2"]
        if normalized_state in {"on_hold", "on hold"}:
            return ["state=3"]
        return [f"state={_sanitize_query_value(normalized_state)}"]

from __future__ import annotations


def compact_text(value: str | None, limit: int = 500) -> str:
    if value is None:
        return ""
    compacted = " ".join(str(value).split())
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 3]}..."

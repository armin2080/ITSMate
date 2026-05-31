from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from requests import RequestException
from django.conf import settings

from apps.servicenow.client import ServiceNowClient


class ServiceNowOAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class ServiceNowIdentity:
    username: str
    display_name: str = ""
    email: str = ""
    claims: dict[str, Any] = field(default_factory=dict)


class ServiceNowOAuthService:
    def __init__(self) -> None:
        self.instance_url = settings.SERVICENOW_INSTANCE_URL.rstrip("/")
        self.client_id = settings.SERVICENOW_OAUTH_CLIENT_ID.strip()
        self.client_secret = settings.SERVICENOW_OAUTH_CLIENT_SECRET.strip()
        self.authorization_url = settings.SERVICENOW_OAUTH_AUTH_URL.strip() or f"{self.instance_url}/oauth_auth.do"
        self.token_url = settings.SERVICENOW_OAUTH_TOKEN_URL.strip() or f"{self.instance_url}/oauth_token.do"
        self.redirect_uri = settings.SERVICENOW_OAUTH_REDIRECT_URI.strip()
        self.scope = settings.SERVICENOW_OAUTH_SCOPE.strip() or "openid profile email"
        self.timeout = settings.SERVICENOW_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def build_authorization_url(self, *, state: str) -> str:
        self._ensure_configured()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        return f"{self.authorization_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        self._ensure_configured()
        try:
            response = requests.post(
                self.token_url,
                auth=(self.client_id, self.client_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except RequestException as exc:
            raise ServiceNowOAuthError(f"Could not reach ServiceNow OAuth endpoint: {exc}") from exc
        if not response.ok:
            raise ServiceNowOAuthError(self._format_http_error(response))
        token_data = response.json()
        if not isinstance(token_data, dict):
            raise ServiceNowOAuthError("ServiceNow returned an unexpected OAuth response.")
        if not token_data.get("access_token"):
            raise ServiceNowOAuthError("ServiceNow did not return an access token.")
        return token_data

    def resolve_identity(self, token_data: dict[str, Any]) -> ServiceNowIdentity:
        id_token = str(token_data.get("id_token") or "").strip()
        if not id_token:
            raise ServiceNowOAuthError(
                "ServiceNow did not return an OpenID Connect id_token. Make sure the OAuth app includes the openid scope."
            )

        claims = self._decode_id_token(id_token)
        self._validate_claims(claims)

        candidate = str(claims.get("preferred_username") or claims.get("email") or "").strip()
        if not candidate:
            raise ServiceNowOAuthError("ServiceNow did not include a preferred username or email claim.")

        client = ServiceNowClient(access_token=str(token_data["access_token"]))
        try:
            user_record = client.get_user_record(candidate)
        except RequestException as exc:
            raise ServiceNowOAuthError(f"Could not load the ServiceNow user record: {exc}") from exc
        if not user_record:
            raise ServiceNowOAuthError("The ServiceNow account in the token could not be matched to a sys_user record.")

        username = str(user_record.get("user_name") or candidate).strip()
        display_name = str(user_record.get("name") or claims.get("name") or "").strip()
        email = str(user_record.get("email") or claims.get("email") or "").strip()
        return ServiceNowIdentity(username=username, display_name=display_name, email=email, claims=claims)

    def _decode_id_token(self, id_token: str) -> dict[str, Any]:
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ServiceNowOAuthError("ServiceNow returned an invalid id_token.")
        payload = self._base64url_decode(parts[1])
        try:
            claims = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ServiceNowOAuthError("ServiceNow returned unreadable identity claims.") from exc
        if not isinstance(claims, dict):
            raise ServiceNowOAuthError("ServiceNow returned unexpected identity claims.")
        return claims

    def _validate_claims(self, claims: dict[str, Any]) -> None:
        issuer = str(claims.get("iss") or "").rstrip("/")
        if issuer and issuer != self.instance_url and not issuer.startswith(self.instance_url):
            raise ServiceNowOAuthError("ServiceNow token issuer did not match the configured instance.")

        audience = claims.get("aud")
        if isinstance(audience, str):
            aud_matches = audience == self.client_id
        elif isinstance(audience, list):
            aud_matches = self.client_id in audience
        else:
            aud_matches = False
        if audience and not aud_matches:
            raise ServiceNowOAuthError("ServiceNow token audience did not match the configured client id.")

        expires_at = claims.get("exp")
        if isinstance(expires_at, int) and datetime.now(timezone.utc).timestamp() >= expires_at:
            raise ServiceNowOAuthError("ServiceNow token has expired.")

    def _base64url_decode(self, value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))

    def _format_http_error(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text.strip()
        return f"ServiceNow OAuth request failed with {response.status_code}: {payload}"

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise ServiceNowOAuthError(
                "ServiceNow OAuth is not configured. Set SERVICENOW_OAUTH_CLIENT_ID, SERVICENOW_OAUTH_CLIENT_SECRET, and SERVICENOW_OAUTH_REDIRECT_URI."
            )
from __future__ import annotations

import os
import secrets
from typing import Optional

import jwt
import requests


class XeroOAuth2:
    """Xero OAuth2 handler for Flask.

    SECURITY: client_secret 仅在服务端 token exchange 和 refresh 时使用，
    绝不传入模板或 API 响应，避免暴露到前端。
    """

    XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
    XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
    XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
    XERO_IDENTITY_URL = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("XERO_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("XERO_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("XERO_REDIRECT_URI")

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            raise ValueError("Missing Xero OAuth2 credentials")

    def get_authorization_url(self, state: Optional[str] = None, scopes: Optional[list[str]] = None) -> str:
        """Generate Xero authorization URL."""
        state = state or secrets.token_urlsafe(32)
        scopes = scopes or ["offline_access", "openid", "profile", "email"]

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
        import urllib.parse
        return f"{self.XERO_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token.

        client_secret 仅在此服务端调用中使用，不暴露到前端。
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        response = requests.post(self.XERO_TOKEN_URL, data=data, timeout=10)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            print(f"[DEBUG] Token request failed: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text}")
            raise exc
        return response.json()

    def refresh_access_token(self, refresh_token: str) -> dict:
        """使用 refresh_token 获取新的 access_token。"""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(self.XERO_TOKEN_URL, data=data, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_connections(self, access_token: str) -> list[dict]:
        """获取用户有权限访问的 Xero organization 列表。

        返回示例: [{"id": "...", "tenantId": "...", "tenantName": "...", "tenantType": "ORGANISATION"}]
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.XERO_CONNECTIONS_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_user_info(self, access_token: str) -> dict:
        """Fetch user info from ID token."""
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.XERO_IDENTITY_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def decode_id_token(self, id_token: str) -> dict:
        """Decode ID token (without verification for now)."""
        try:
            # Decode without verification (token is from trusted Xero)
            return jwt.decode(id_token, options={"verify_signature": False})
        except Exception as exc:
            print(f"Failed to decode ID token: {exc}")
            return {}

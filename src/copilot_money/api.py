from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from copilot_money.config import load_config, save_config

GRAPHQL_ENDPOINT = "https://api.copilot.money/graphql"
# Public Firebase client API key (same as Copilot Money web app uses - not a secret)
FIREBASE_TOKEN_ENDPOINT = (
    "https://securetoken.googleapis.com/v1/token"
    "?key=AIzaSyAMgjkeOSkHj4J4rlswOkD16N3WQOoNPpk"
)


class CopilotAPI:
    def __init__(self) -> None:
        self.config = load_config()
        self.client = httpx.Client(timeout=30)

    def close(self) -> None:
        self.client.close()

    def get_access_token(self) -> str:
        if self.config.is_access_token_valid():
            return self.config.access_token or ""
        return self.refresh_access_token()

    def refresh_access_token(self) -> str:
        if not self.config.refresh_token:
            raise RuntimeError(
                "Missing refresh token. Run 'copilot config init' first."
            )
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.config.refresh_token,
        }
        response = self.client.post(
            FIREBASE_TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")
        if not access_token or not refresh_token or not expires_in:
            raise RuntimeError("Invalid token response from Firebase.")
        now = datetime.now(timezone.utc).timestamp()
        self.config.access_token = access_token
        self.config.refresh_token = refresh_token
        self.config.expires_at = now + float(expires_in)
        save_config(self.config)
        return access_token

    def query(self, query: str) -> Dict[str, Any]:
        token = self.get_access_token()
        response = self.client.post(
            GRAPHQL_ENDPOINT,
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            raise RuntimeError(f"GraphQL error: {payload['errors']}")
        return payload.get("data", {})

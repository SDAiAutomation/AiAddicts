"""Microsoft Graph API client for SharePoint operations (Phase 2)."""
import logging
from urllib.parse import urlparse

import requests

from config.settings import settings

logger = logging.getLogger(__name__)
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self):
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token

        url = (
            f"https://login.microsoftonline.com/{settings.sp_tenant_id}"
            "/oauth2/v2.0/token"
        )
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.sp_client_id,
                "client_secret": settings.sp_client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def get_site_id(self) -> str:
        parsed = urlparse(settings.sp_site_url)
        url = f"{GRAPH_BASE}/sites/{parsed.hostname}:{parsed.path}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]

    def get_fi_drive_id(self, site_id: str) -> str | None:
        resp = requests.get(
            f"{GRAPH_BASE}/sites/{site_id}/drives",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        for drive in resp.json().get("value", []):
            if drive["name"] == settings.sp_library_name:
                return drive["id"]
        return None

    def list_fi_documents(self, site_id: str) -> list[dict]:
        drive_id = self.get_fi_drive_id(site_id)
        if not drive_id:
            logger.error("Library '%s' not found.", settings.sp_library_name)
            return []

        resp = requests.get(
            f"{GRAPH_BASE}/drives/{drive_id}/root/children",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def download_file(self, download_url: str) -> bytes:
        resp = requests.get(download_url, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.content

    def update_fi_columns(
        self, site_id: str, drive_id: str, item_id: str, columns: dict
    ) -> None:
        url = (
            f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/listItem/fields"
        )
        resp = requests.patch(url, json=columns, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        logger.info("Updated SP columns for item %s.", item_id)

"""
Central Reach API client.

Authentication: OAuth2 client credentials using ClientId + ClientSecret.
API key sent as a header on every request.

Required env vars:
    CR_CLIENT_ID
    CR_CLIENT_SECRET
    CR_API_KEY
    CR_BASE_URL  (defaults to https://api.centralreach.com)
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class CRUser:
    cr_id: str
    first_name: str
    last_name: str
    email: str
    is_active: bool
    job_title: str = ""
    department: str = ""
    paylocity_id: str = ""   # stored in CR custom field for cross-referencing


class CentralReachClient:
    def __init__(self):
        self.base_url = settings.CR_BASE_URL.rstrip("/")
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            f"{self.base_url}/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.CR_CLIENT_ID,
                "client_secret": settings.CR_CLIENT_SECRET,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "X-Api-Key": settings.CR_API_KEY,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict | list:
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: dict) -> dict:
        resp = requests.patch(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_all_staff(self) -> list[CRUser]:
        """Return all staff members from Central Reach."""
        users: list[CRUser] = []
        page = 1
        while True:
            data = self._get("/api/v1/staff", params={"page": page, "pageSize": 100})
            items = data.get("items", data) if isinstance(data, dict) else data
            if not items:
                break
            for raw in items:
                users.append(self._parse_user(raw))
            if len(items) < 100:
                break
            page += 1

        logger.info("Fetched %d staff from Central Reach", len(users))
        return users

    def get_staff_by_email(self, email: str) -> Optional[CRUser]:
        """Look up a staff member by email address."""
        data = self._get("/api/v1/staff", params={"email": email})
        items = data.get("items", data) if isinstance(data, dict) else data
        if items:
            return self._parse_user(items[0])
        return None

    def create_staff(self, first_name: str, last_name: str, email: str,
                     job_title: str = "", department: str = "",
                     paylocity_id: str = "") -> CRUser:
        """Create a new staff member in Central Reach."""
        body = {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "jobTitle": job_title,
            "department": department,
            "isActive": True,
            "customFields": {"paylocityId": paylocity_id},
        }
        result = self._post("/api/v1/staff", body)
        logger.info("Created CR staff: %s %s (%s)", first_name, last_name, email)
        return self._parse_user(result)

    def update_staff(self, cr_id: str, **fields) -> CRUser:
        """Update an existing staff member's fields."""
        body = {}
        field_map = {
            "first_name": "firstName",
            "last_name": "lastName",
            "email": "email",
            "job_title": "jobTitle",
            "department": "department",
            "is_active": "isActive",
        }
        for py_key, cr_key in field_map.items():
            if py_key in fields:
                body[cr_key] = fields[py_key]

        result = self._patch(f"/api/v1/staff/{cr_id}", body)
        logger.info("Updated CR staff %s", cr_id)
        return self._parse_user(result)

    def deactivate_staff(self, cr_id: str) -> None:
        """Deactivate (soft-delete) a staff member."""
        self._patch(f"/api/v1/staff/{cr_id}", {"isActive": False})
        logger.info("Deactivated CR staff %s", cr_id)

    def reactivate_staff(self, cr_id: str) -> None:
        """Reactivate a previously deactivated staff member."""
        self._patch(f"/api/v1/staff/{cr_id}", {"isActive": True})
        logger.info("Reactivated CR staff %s", cr_id)

    def _parse_user(self, raw: dict) -> CRUser:
        custom = raw.get("customFields") or {}
        return CRUser(
            cr_id=str(raw.get("id", "")),
            first_name=raw.get("firstName", ""),
            last_name=raw.get("lastName", ""),
            email=raw.get("email", ""),
            is_active=raw.get("isActive", True),
            job_title=raw.get("jobTitle", ""),
            department=raw.get("department", ""),
            paylocity_id=custom.get("paylocityId", ""),
        )

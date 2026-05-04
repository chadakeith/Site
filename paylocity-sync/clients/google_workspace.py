"""
Google Workspace Admin SDK client (Directory API).

Authentication: Service account with domain-wide delegation.

Required env vars:
    GOOGLE_SERVICE_ACCOUNT_JSON   path to service account key file, OR
    GOOGLE_SERVICE_ACCOUNT_KEY    raw JSON string of the service account key
    GOOGLE_ADMIN_EMAIL            impersonated super-admin email
    GOOGLE_DOMAIN                 e.g. projecthopesc.org

Setup steps:
    1. Create a GCP project and enable the Admin SDK API.
    2. Create a service account and download its JSON key.
    3. In Google Admin > Security > API Controls > Domain-wide Delegation,
       grant the service account the scope:
       https://www.googleapis.com/auth/admin.directory.user
    4. Set GOOGLE_ADMIN_EMAIL to a super-admin account in your domain.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/admin.directory.user"]


@dataclass
class GoogleUser:
    google_id: str
    first_name: str
    last_name: str
    email: str
    is_suspended: bool
    org_unit: str = ""
    job_title: str = ""
    department: str = ""


class GoogleWorkspaceClient:
    def __init__(self):
        self.domain = settings.GOOGLE_DOMAIN
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service

        # Load key from file path or raw JSON env var
        if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
            with open(settings.GOOGLE_SERVICE_ACCOUNT_JSON) as f:
                key_data = json.load(f)
        elif settings.GOOGLE_SERVICE_ACCOUNT_KEY:
            key_data = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_KEY)
        else:
            raise EnvironmentError(
                "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_KEY"
            )

        creds = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=SCOPES,
            subject=settings.GOOGLE_ADMIN_EMAIL,
        )
        self._service = build("admin", "directory_v1", credentials=creds)
        return self._service

    def get_all_users(self) -> list[GoogleUser]:
        """Return all users in the domain."""
        svc = self._get_service()
        users: list[GoogleUser] = []
        page_token = None

        while True:
            result = (
                svc.users()
                .list(
                    domain=self.domain,
                    maxResults=500,
                    orderBy="email",
                    pageToken=page_token,
                )
                .execute()
            )
            for raw in result.get("users", []):
                users.append(self._parse_user(raw))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info("Fetched %d users from Google Workspace", len(users))
        return users

    def get_user(self, email: str) -> Optional[GoogleUser]:
        """Look up a user by primary email. Returns None if not found."""
        svc = self._get_service()
        try:
            raw = svc.users().get(userKey=email).execute()
            return self._parse_user(raw)
        except HttpError as e:
            if e.resp.status == 404:
                return None
            raise

    def create_user(self, first_name: str, last_name: str, email: str,
                    temp_password: str, job_title: str = "",
                    department: str = "", org_unit: str = "/") -> GoogleUser:
        """Create a new Google Workspace user."""
        svc = self._get_service()
        body = {
            "name": {"givenName": first_name, "familyName": last_name},
            "primaryEmail": email,
            "password": temp_password,
            "changePasswordAtNextLogin": True,
            "orgUnitPath": org_unit,
            "organizations": [
                {
                    "title": job_title,
                    "department": department,
                    "primary": True,
                }
            ],
        }
        raw = svc.users().insert(body=body).execute()
        logger.info("Created Google user: %s", email)
        return self._parse_user(raw)

    def update_user(self, email: str, **fields) -> GoogleUser:
        """Update an existing user's profile fields."""
        svc = self._get_service()
        body: dict = {}

        if "first_name" in fields or "last_name" in fields:
            existing = self.get_user(email)
            body["name"] = {
                "givenName": fields.get("first_name", existing.first_name if existing else ""),
                "familyName": fields.get("last_name", existing.last_name if existing else ""),
            }

        if "job_title" in fields or "department" in fields:
            body["organizations"] = [
                {
                    "title": fields.get("job_title", ""),
                    "department": fields.get("department", ""),
                    "primary": True,
                }
            ]

        if "org_unit" in fields:
            body["orgUnitPath"] = fields["org_unit"]

        raw = svc.users().update(userKey=email, body=body).execute()
        logger.info("Updated Google user: %s", email)
        return self._parse_user(raw)

    def suspend_user(self, email: str) -> None:
        """Suspend a user account (employee terminated)."""
        svc = self._get_service()
        svc.users().update(userKey=email, body={"suspended": True}).execute()
        logger.info("Suspended Google user: %s", email)

    def restore_user(self, email: str) -> None:
        """Unsuspend a user account (employee rehired)."""
        svc = self._get_service()
        svc.users().update(userKey=email, body={"suspended": False}).execute()
        logger.info("Restored Google user: %s", email)

    def _parse_user(self, raw: dict) -> GoogleUser:
        name = raw.get("name", {})
        orgs = raw.get("organizations", [{}])
        org = orgs[0] if orgs else {}
        return GoogleUser(
            google_id=raw.get("id", ""),
            first_name=name.get("givenName", ""),
            last_name=name.get("familyName", ""),
            email=raw.get("primaryEmail", ""),
            is_suspended=raw.get("suspended", False),
            org_unit=raw.get("orgUnitPath", "/"),
            job_title=org.get("title", ""),
            department=org.get("department", ""),
        )

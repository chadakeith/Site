"""
Paylocity API client.

Authentication: OAuth2 client credentials flow.
Docs: https://developer.paylocity.com/integrations/reference/

Required env vars:
    PAYLOCITY_CLIENT_ID
    PAYLOCITY_CLIENT_SECRET
    PAYLOCITY_COMPANY_ID
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.paylocity.com/IdentityServer/connect/token"
BASE_URL = "https://api.paylocity.com/api"


@dataclass
class Employee:
    employee_id: str
    first_name: str
    last_name: str
    email: str
    status: str          # "Active" | "Terminated" | "Leave"
    job_title: str = ""
    department: str = ""
    location: str = ""
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    manager_email: str = ""
    custom_fields: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        return self.status == "Active"


class PaylocityClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self.company_id = settings.PAYLOCITY_COMPANY_ID

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.PAYLOCITY_CLIENT_ID,
                "client_secret": settings.PAYLOCITY_CLIENT_SECRET,
                "scope": "WebLinkAPI",
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
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_all_employees(self) -> list[Employee]:
        """Return every employee in the company (all pages)."""
        employees = []
        page = 1
        while True:
            data = self._get(
                f"/v2/companies/{self.company_id}/employees",
                params={"pagesize": 100, "pagenumber": page},
            )
            if not data:
                break
            for raw in data:
                employees.append(self._parse_employee(raw))
            if len(data) < 100:
                break
            page += 1

        logger.info("Fetched %d employees from Paylocity", len(employees))
        return employees

    def get_employee(self, employee_id: str) -> Employee:
        """Return a single employee by Paylocity employee ID."""
        data = self._get(f"/v2/companies/{self.company_id}/employees/{employee_id}")
        return self._parse_employee(data)

    def _parse_employee(self, raw: dict) -> Employee:
        primary = raw.get("primaryPayRate", {})
        hire_date = None
        if raw.get("hireDate"):
            try:
                hire_date = date.fromisoformat(raw["hireDate"][:10])
            except ValueError:
                pass

        term_date = None
        if raw.get("terminationDate"):
            try:
                term_date = date.fromisoformat(raw["terminationDate"][:10])
            except ValueError:
                pass

        return Employee(
            employee_id=str(raw.get("employeeId", "")),
            first_name=raw.get("firstName", ""),
            last_name=raw.get("lastName", ""),
            email=raw.get("workEmail", "") or raw.get("personalEmail", ""),
            status=raw.get("status", "Unknown"),
            job_title=primary.get("jobTitle", ""),
            department=raw.get("department", {}).get("departmentName", ""),
            location=raw.get("location", {}).get("locationName", ""),
            hire_date=hire_date,
            termination_date=term_date,
            manager_email=raw.get("supervisorWorkEmail", ""),
        )

    # ------------------------------------------------------------------
    # Webhook helpers
    # ------------------------------------------------------------------

    @staticmethod
    def parse_webhook_payload(payload: dict) -> tuple[str, dict]:
        """
        Extract (event_type, employee_data) from a Paylocity webhook payload.

        Paylocity sends events like:
            {"eventType": "EmployeeHired", "employee": {...}}
            {"eventType": "EmployeeUpdated", "employee": {...}}
            {"eventType": "EmployeeTerminated", "employee": {...}}
        """
        event_type = payload.get("eventType", "")
        employee_data = payload.get("employee", {})
        return event_type, employee_data

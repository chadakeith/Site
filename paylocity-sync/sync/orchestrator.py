"""
Sync orchestrator: compares Paylocity employees against Central Reach and
Google Workspace, then applies the minimum set of changes needed.

DRY_RUN mode (default: True) logs every planned action without touching any
external system. Set DRY_RUN=false in env (or pass dry_run=False) only after
you have verified connections with test_connections.py.
"""

import logging
import os
import secrets
import string
from dataclasses import dataclass
from typing import Optional

from clients.paylocity import Employee, PaylocityClient
from clients.central_reach import CRUser, CentralReachClient
from clients.google_workspace import GoogleUser, GoogleWorkspaceClient
from config import settings

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"


@dataclass
class SyncResult:
    created_cr: list[str] = None
    updated_cr: list[str] = None
    deactivated_cr: list[str] = None
    created_google: list[str] = None
    updated_google: list[str] = None
    suspended_google: list[str] = None
    errors: list[str] = None

    def __post_init__(self):
        for f in ("created_cr", "updated_cr", "deactivated_cr",
                  "created_google", "updated_google", "suspended_google", "errors"):
            if getattr(self, f) is None:
                setattr(self, f, [])

    def summary(self) -> str:
        return (
            f"Central Reach  — created: {len(self.created_cr)}, "
            f"updated: {len(self.updated_cr)}, deactivated: {len(self.deactivated_cr)}\n"
            f"Google         — created: {len(self.created_google)}, "
            f"updated: {len(self.updated_google)}, suspended: {len(self.suspended_google)}\n"
            f"Errors         — {len(self.errors)}"
        )


def _temp_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$"
    return "".join(secrets.choice(alphabet) for _ in range(16))


class SyncOrchestrator:
    def __init__(
        self,
        paylocity: Optional[PaylocityClient] = None,
        central_reach: Optional[CentralReachClient] = None,
        google: Optional[GoogleWorkspaceClient] = None,
        dry_run: Optional[bool] = None,
    ):
        self.paylocity = paylocity or PaylocityClient()
        self.central_reach = central_reach or CentralReachClient()
        self.google = google or GoogleWorkspaceClient()
        self.dry_run = DRY_RUN if dry_run is None else dry_run

        if self.dry_run:
            logger.warning(
                "DRY_RUN is ON — no data will be created, updated, or deleted. "
                "Set DRY_RUN=false to apply changes."
            )

    # ──────────────────────────────────────────────────────────────────
    # Main entry points
    # ──────────────────────────────────────────────────────────────────

    def full_sync(self) -> SyncResult:
        """Pull all employees from Paylocity and reconcile with CR + Google."""
        logger.info("=== Starting full sync (dry_run=%s) ===", self.dry_run)
        result = SyncResult()

        try:
            employees = self.paylocity.get_all_employees()
        except Exception as exc:
            logger.error("Failed to fetch employees from Paylocity: %s", exc)
            result.errors.append(f"Paylocity fetch failed: {exc}")
            return result

        # Build lookup maps keyed by email
        try:
            cr_users = {u.email.lower(): u for u in self.central_reach.get_all_staff()}
        except Exception as exc:
            logger.error("Failed to fetch staff from Central Reach: %s", exc)
            result.errors.append(f"Central Reach fetch failed: {exc}")
            cr_users = {}

        try:
            google_users = {u.email.lower(): u for u in self.google.get_all_users()}
        except Exception as exc:
            logger.error("Failed to fetch users from Google Workspace: %s", exc)
            result.errors.append(f"Google fetch failed: {exc}")
            google_users = {}

        for emp in employees:
            try:
                self._sync_to_cr(emp, cr_users, result)
            except Exception as exc:
                msg = f"CR sync error for {emp.email}: {exc}"
                logger.error(msg)
                result.errors.append(msg)

            try:
                self._sync_to_google(emp, google_users, result)
            except Exception as exc:
                msg = f"Google sync error for {emp.email}: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        logger.info("=== Sync complete ===\n%s", result.summary())
        return result

    def sync_one(self, paylocity_employee_id: str) -> SyncResult:
        """Sync a single employee — used when a webhook fires for one person."""
        logger.info("Syncing single employee %s (dry_run=%s)", paylocity_employee_id, self.dry_run)
        result = SyncResult()

        try:
            emp = self.paylocity.get_employee(paylocity_employee_id)
        except Exception as exc:
            result.errors.append(f"Failed to fetch employee {paylocity_employee_id}: {exc}")
            return result

        key = emp.email.lower()

        try:
            cr_user = self.central_reach.get_staff_by_email(emp.email)
            cr_users = {key: cr_user} if cr_user else {}
            self._sync_to_cr(emp, cr_users, result)
        except Exception as exc:
            result.errors.append(f"CR sync error for {emp.email}: {exc}")

        try:
            g_user = self.google.get_user(emp.email)
            google_users = {key: g_user} if g_user else {}
            self._sync_to_google(emp, google_users, result)
        except Exception as exc:
            result.errors.append(f"Google sync error for {emp.email}: {exc}")

        logger.info("Single-employee sync complete\n%s", result.summary())
        return result

    # ──────────────────────────────────────────────────────────────────
    # Internal sync logic
    # ──────────────────────────────────────────────────────────────────

    def _sync_to_cr(self, emp: Employee, cr_map: dict[str, CRUser], result: SyncResult):
        key = emp.email.lower()
        existing = cr_map.get(key)

        if emp.is_active:
            if not existing:
                logger.info("[DRY_RUN=%s] CREATE CR user: %s", self.dry_run, emp.email)
                if not self.dry_run:
                    self.central_reach.create_staff(
                        first_name=emp.first_name,
                        last_name=emp.last_name,
                        email=emp.email,
                        job_title=emp.job_title,
                        department=emp.department,
                        paylocity_id=emp.employee_id,
                    )
                result.created_cr.append(emp.email)
            else:
                changes = self._cr_diff(emp, existing)
                if changes:
                    logger.info("[DRY_RUN=%s] UPDATE CR user %s: %s", self.dry_run, emp.email, changes)
                    if not self.dry_run:
                        self.central_reach.update_staff(existing.cr_id, **changes)
                    result.updated_cr.append(emp.email)

                if not existing.is_active:
                    logger.info("[DRY_RUN=%s] REACTIVATE CR user: %s", self.dry_run, emp.email)
                    if not self.dry_run:
                        self.central_reach.reactivate_staff(existing.cr_id)
                    result.updated_cr.append(emp.email)
        else:
            # Terminated — deactivate if currently active
            if existing and existing.is_active:
                logger.info("[DRY_RUN=%s] DEACTIVATE CR user: %s", self.dry_run, emp.email)
                if not self.dry_run:
                    self.central_reach.deactivate_staff(existing.cr_id)
                result.deactivated_cr.append(emp.email)

    def _sync_to_google(self, emp: Employee, google_map: dict[str, GoogleUser], result: SyncResult):
        key = emp.email.lower()
        existing = google_map.get(key)

        if emp.is_active:
            if not existing:
                pwd = _temp_password()
                logger.info("[DRY_RUN=%s] CREATE Google user: %s (temp password generated)", self.dry_run, emp.email)
                if not self.dry_run:
                    self.google.create_user(
                        first_name=emp.first_name,
                        last_name=emp.last_name,
                        email=emp.email,
                        temp_password=pwd,
                        job_title=emp.job_title,
                        department=emp.department,
                    )
                result.created_google.append(emp.email)
            else:
                changes = self._google_diff(emp, existing)
                if changes:
                    logger.info("[DRY_RUN=%s] UPDATE Google user %s: %s", self.dry_run, emp.email, changes)
                    if not self.dry_run:
                        self.google.update_user(emp.email, **changes)
                    result.updated_google.append(emp.email)

                if existing.is_suspended:
                    logger.info("[DRY_RUN=%s] RESTORE Google user: %s", self.dry_run, emp.email)
                    if not self.dry_run:
                        self.google.restore_user(emp.email)
                    result.updated_google.append(emp.email)
        else:
            if existing and not existing.is_suspended:
                logger.info("[DRY_RUN=%s] SUSPEND Google user: %s", self.dry_run, emp.email)
                if not self.dry_run:
                    self.google.suspend_user(emp.email)
                result.suspended_google.append(emp.email)

    @staticmethod
    def _cr_diff(emp: Employee, cr: CRUser) -> dict:
        changes = {}
        if emp.first_name != cr.first_name:
            changes["first_name"] = emp.first_name
        if emp.last_name != cr.last_name:
            changes["last_name"] = emp.last_name
        if emp.job_title and emp.job_title != cr.job_title:
            changes["job_title"] = emp.job_title
        if emp.department and emp.department != cr.department:
            changes["department"] = emp.department
        return changes

    @staticmethod
    def _google_diff(emp: Employee, g: GoogleUser) -> dict:
        changes = {}
        if emp.first_name != g.first_name:
            changes["first_name"] = emp.first_name
        if emp.last_name != g.last_name:
            changes["last_name"] = emp.last_name
        if emp.job_title and emp.job_title != g.job_title:
            changes["job_title"] = emp.job_title
        if emp.department and emp.department != g.department:
            changes["department"] = emp.department
        return changes

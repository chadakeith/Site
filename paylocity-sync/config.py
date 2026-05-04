"""Centralised settings loaded from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # ── Paylocity ──────────────────────────────────────────────────────
    PAYLOCITY_CLIENT_ID: str = field(default_factory=lambda: os.getenv("PAYLOCITY_CLIENT_ID", ""))
    PAYLOCITY_CLIENT_SECRET: str = field(default_factory=lambda: os.getenv("PAYLOCITY_CLIENT_SECRET", ""))
    PAYLOCITY_COMPANY_ID: str = field(default_factory=lambda: os.getenv("PAYLOCITY_COMPANY_ID", ""))

    # ── Central Reach ──────────────────────────────────────────────────
    CR_CLIENT_ID: str = field(default_factory=lambda: os.getenv("CR_CLIENT_ID", ""))
    CR_CLIENT_SECRET: str = field(default_factory=lambda: os.getenv("CR_CLIENT_SECRET", ""))
    CR_API_KEY: str = field(default_factory=lambda: os.getenv("CR_API_KEY", ""))
    CR_BASE_URL: str = field(default_factory=lambda: os.getenv("CR_BASE_URL", "https://api.centralreach.com"))

    # ── Google Workspace ───────────────────────────────────────────────
    # Provide either a file path (local) or the raw JSON string (CI/CD)
    GOOGLE_SERVICE_ACCOUNT_JSON: str = field(default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    GOOGLE_SERVICE_ACCOUNT_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", ""))
    GOOGLE_ADMIN_EMAIL: str = field(default_factory=lambda: os.getenv("GOOGLE_ADMIN_EMAIL", ""))
    GOOGLE_DOMAIN: str = field(default_factory=lambda: os.getenv("GOOGLE_DOMAIN", ""))

    # ── Default new-user password (forced change on first login) ───────
    DEFAULT_TEMP_PASSWORD: str = field(
        default_factory=lambda: os.getenv("DEFAULT_TEMP_PASSWORD", "ChangeMe2024!")
    )

    # ── Sync behaviour ─────────────────────────────────────────────────
    # Comma-separated list of Paylocity statuses treated as "active"
    ACTIVE_STATUSES: list[str] = field(
        default_factory=lambda: os.getenv("ACTIVE_STATUSES", "Active").split(",")
    )

    def validate(self, require_paylocity: bool = True) -> None:
        """Raise if any required vars are missing."""
        errors = []

        if require_paylocity:
            for var in ("PAYLOCITY_CLIENT_ID", "PAYLOCITY_CLIENT_SECRET", "PAYLOCITY_COMPANY_ID"):
                if not getattr(self, var):
                    errors.append(var)

        for var in ("CR_CLIENT_ID", "CR_CLIENT_SECRET", "CR_API_KEY"):
            if not getattr(self, var):
                errors.append(var)

        for var in ("GOOGLE_ADMIN_EMAIL", "GOOGLE_DOMAIN"):
            if not getattr(self, var):
                errors.append(var)

        if not self.GOOGLE_SERVICE_ACCOUNT_JSON and not self.GOOGLE_SERVICE_ACCOUNT_KEY:
            errors.append("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_KEY")

        if errors:
            raise EnvironmentError(
                "Missing required environment variables:\n  " + "\n  ".join(errors)
            )


settings = Settings()

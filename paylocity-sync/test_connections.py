"""
Run this first — before any sync — to verify that all API credentials
are correct and each system responds.

Usage:
    python test_connections.py [--skip-paylocity] [--skip-cr] [--skip-google]

Exit code 0 = all tested systems OK.
Exit code 1 = one or more failures.
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def test_central_reach() -> bool:
    from clients.central_reach import CentralReachClient
    logger.info("── Central Reach ──────────────────────────────")
    try:
        cr = CentralReachClient()
        staff = cr.get_all_staff()
        logger.info("  ✓ Connected. Found %d staff members.", len(staff))
        if staff:
            sample = staff[0]
            logger.info(
                "  Sample: %s %s (%s) — active=%s",
                sample.first_name, sample.last_name, sample.email, sample.is_active,
            )
        return True
    except Exception as exc:
        logger.error("  ✗ Central Reach connection failed: %s", exc)
        return False


def test_google() -> bool:
    from clients.google_workspace import GoogleWorkspaceClient
    logger.info("── Google Workspace ────────────────────────────")
    try:
        gws = GoogleWorkspaceClient()
        users = gws.get_all_users()
        logger.info("  ✓ Connected. Found %d users.", len(users))
        if users:
            sample = users[0]
            logger.info(
                "  Sample: %s %s (%s) — suspended=%s",
                sample.first_name, sample.last_name, sample.email, sample.is_suspended,
            )
        return True
    except Exception as exc:
        logger.error("  ✗ Google Workspace connection failed: %s", exc)
        return False


def test_paylocity() -> bool:
    from clients.paylocity import PaylocityClient
    logger.info("── Paylocity ───────────────────────────────────")
    try:
        plc = PaylocityClient()
        employees = plc.get_all_employees()
        logger.info("  ✓ Connected. Found %d employees.", len(employees))
        if employees:
            sample = employees[0]
            logger.info(
                "  Sample: %s %s (%s) — status=%s",
                sample.first_name, sample.last_name, sample.email, sample.status,
            )
        return True
    except Exception as exc:
        logger.error("  ✗ Paylocity connection failed: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="Test API connections")
    parser.add_argument("--skip-paylocity", action="store_true")
    parser.add_argument("--skip-cr", action="store_true")
    parser.add_argument("--skip-google", action="store_true")
    args = parser.parse_args()

    logger.info("=== Connection Tests (READ-ONLY — no data will change) ===\n")
    results = []

    if not args.skip_paylocity:
        results.append(("Paylocity", test_paylocity()))

    if not args.skip_cr:
        results.append(("Central Reach", test_central_reach()))

    if not args.skip_google:
        results.append(("Google Workspace", test_google()))

    logger.info("\n=== Results ===")
    all_ok = True
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        logger.info("  %s  %s", status, name)
        if not ok:
            all_ok = False

    if all_ok:
        logger.info("\nAll connections OK. You can now run the sync.")
        sys.exit(0)
    else:
        logger.error("\nOne or more connections failed. Fix credentials before running sync.")
        sys.exit(1)


if __name__ == "__main__":
    main()

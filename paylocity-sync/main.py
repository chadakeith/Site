"""
Main entrypoint for the Paylocity → Central Reach + Google sync.

Modes:
    full        Pull all employees from Paylocity and reconcile (default)
    employee    Sync a single employee by Paylocity employee ID

Environment:
    DRY_RUN=true   (default) Log planned changes without touching anything
    DRY_RUN=false  Apply changes — only use after test_connections.py passes

Usage:
    python main.py full
    python main.py employee 12345
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Paylocity sync")
    sub = parser.add_subparsers(dest="mode", required=False)

    sub.add_parser("full", help="Full sync of all employees")

    emp_parser = sub.add_parser("employee", help="Sync one employee by ID")
    emp_parser.add_argument("employee_id", help="Paylocity employee ID")

    args = parser.parse_args()
    mode = args.mode or "full"

    from sync.orchestrator import SyncOrchestrator
    orchestrator = SyncOrchestrator()

    if mode == "full":
        result = orchestrator.full_sync()
    elif mode == "employee":
        result = orchestrator.sync_one(args.employee_id)
    else:
        parser.print_help()
        sys.exit(1)

    if result.errors:
        logger.warning("Completed with %d error(s):", len(result.errors))
        for err in result.errors:
            logger.warning("  - %s", err)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

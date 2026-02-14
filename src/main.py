"""Main entry point for Call Tracking Calendar."""

import argparse
import sys

from .launchagent import is_installed as launchagent_installed
from .permissions import check_full_disk_access
from .sync_database import SyncDatabase


def is_setup_complete() -> bool:
    """Check if initial setup has been completed.

    Returns:
        True if setup is complete, False otherwise.
    """
    sync_db = SyncDatabase()
    if not sync_db.db_path.exists():
        return False

    # Check the setup_complete flag — no keychain access, no prompts
    try:
        sync_db.initialize()
        return sync_db.get_setting("setup_complete") == "true"
    except Exception:
        return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Call Tracking Calendar - Sync macOS calls to Google Calendar"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Force run the setup wizard",
    )
    parser.add_argument(
        "--preferences",
        action="store_true",
        help="Open preferences window",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run sync immediately",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show sync status",
    )
    args = parser.parse_args()

    # Handle --sync: run sync service
    if args.sync:
        from .sync_service import main as sync_main

        return sync_main()

    # Handle --status: show status
    if args.status:
        from .sync_service import SyncService

        service = SyncService()
        status = service.get_sync_status()

        print("Call Tracking Calendar Status")
        print("=" * 40)
        print(f"Full Disk Access: {'✓' if status['call_db_accessible'] else '✗'}")
        print(f"Google Calendar: {'✓' if status['google_authenticated'] else '✗'}")
        print(f"Background Sync: {'✓' if launchagent_installed() else '✗'}")
        print(f"Synced Calls: {status['synced_calls_count']}")
        print(f"Total Calls: {status['total_calls_count']}")
        return 0

    # Handle --setup or first run: show setup wizard
    if args.setup or not is_setup_complete():
        from .ui.setup_wizard import run_setup_wizard

        run_setup_wizard()
        return 0

    # Default: show preferences window
    from .ui.preferences import run_preferences

    run_preferences()
    return 0


if __name__ == "__main__":
    sys.exit(main())

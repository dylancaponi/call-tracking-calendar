"""Main sync service that orchestrates call syncing to Google Calendar."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional

from .call_database import CallDatabase, CallRecord
from .google_calendar import GoogleCalendar, GoogleCalendarError, AuthenticationError
from .sync_database import SyncDatabase

# Configure logging
LOG_DIR = Path.home() / "Library" / "Logs" / "CallTrackingCalendar"
LOG_FILE = LOG_DIR / "sync.log"

# Default sync period for first sync (30 days)
DEFAULT_SYNC_DAYS = 30

# Setting key for tracking if initial sync was done
SETTING_INITIAL_SYNC_DONE = "initial_sync_done"
SETTING_SYNC_ALL_HISTORY = "sync_all_history"
SETTING_CALENDAR_ID = "calendar_id"


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the sync service."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    calls_synced: int
    calls_skipped: int
    errors: List[str]
    started_at: datetime
    finished_at: datetime

    @property
    def duration_seconds(self) -> float:
        """Get the duration of the sync in seconds."""
        return (self.finished_at - self.started_at).total_seconds()

    def __str__(self) -> str:
        status = "succeeded" if self.success else "failed"
        return (
            f"Sync {status}: {self.calls_synced} synced, "
            f"{self.calls_skipped} skipped, {len(self.errors)} errors "
            f"in {self.duration_seconds:.1f}s"
        )


class SyncService:
    """Orchestrates syncing calls to Google Calendar."""

    def __init__(
        self,
        call_db: Optional[CallDatabase] = None,
        sync_db: Optional[SyncDatabase] = None,
        calendar: Optional[GoogleCalendar] = None,
    ):
        """Initialize the sync service.

        Args:
            call_db: Call database instance (uses default if None).
            sync_db: Sync database instance (uses default if None).
            calendar: Google Calendar instance (uses default if None).
        """
        self.call_db = call_db or CallDatabase()
        self.sync_db = sync_db or SyncDatabase()
        self.calendar = calendar or GoogleCalendar()

    def check_prerequisites(self) -> List[str]:
        """Check if all prerequisites are met for syncing.

        Returns:
            List of error messages, empty if all prerequisites are met.
        """
        errors = []

        # Check call database accessibility
        if not self.call_db.exists():
            errors.append("Call history database not found.")
        elif not self.call_db.is_readable():
            errors.append(
                "Cannot read call history. Full Disk Access permission is required."
            )

        # Check Google Calendar authentication
        if not self.calendar.is_authenticated:
            errors.append("Not authenticated with Google Calendar.")

        return errors

    def _get_default_since(self) -> Optional[datetime]:
        """Get the default 'since' date for syncing.

        Returns 30 days ago for first sync, None for subsequent syncs.
        """
        # Check if user wants all history
        if self.sync_db.get_setting(SETTING_SYNC_ALL_HISTORY) == "true":
            return None

        # Check if initial sync was already done
        if self.sync_db.get_setting(SETTING_INITIAL_SYNC_DONE) == "true":
            return None  # Subsequent syncs get all new calls

        # First sync: default to last 30 days
        return datetime.now(timezone.utc) - timedelta(days=DEFAULT_SYNC_DAYS)

    def set_sync_all_history(self, enabled: bool) -> None:
        """Enable or disable syncing all history.

        Args:
            enabled: If True, sync all history instead of just 30 days.
        """
        self.sync_db.initialize()
        self.sync_db.set_setting(SETTING_SYNC_ALL_HISTORY, "true" if enabled else "false")

    def sync(
        self,
        answered_only: bool = True,
        since: Optional[datetime] = None,
        dry_run: bool = False,
        use_batch: bool = True,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> SyncResult:
        """Perform a sync operation.

        Args:
            answered_only: Only sync answered calls.
            since: Only sync calls after this time. If None, uses default (30 days for
                   first sync, all new calls for subsequent syncs).
            dry_run: If True, don't actually create events.
            use_batch: If True, use batch API for faster syncing.
            on_progress: Optional callback(completed, total) for progress updates.

        Returns:
            SyncResult with details of the sync operation.
        """
        started_at = datetime.now(timezone.utc)
        errors: List[str] = []
        calls_synced = 0
        calls_skipped = 0

        # Initialize sync database
        try:
            self.sync_db.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize sync database: {e}")
            return SyncResult(
                success=False,
                calls_synced=0,
                calls_skipped=0,
                errors=[f"Failed to initialize sync database: {e}"],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # Check prerequisites
        prereq_errors = self.check_prerequisites()
        if prereq_errors:
            return SyncResult(
                success=False,
                calls_synced=0,
                calls_skipped=0,
                errors=prereq_errors,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # Detect if the calendar was deleted and recreated
        try:
            calendar_id = self.calendar.get_calendar_id()
            stored_calendar_id = self.sync_db.get_setting(SETTING_CALENDAR_ID)

            if stored_calendar_id and stored_calendar_id != calendar_id:
                logger.info("Calendar ID changed (calendar was deleted/recreated) — clearing sync history")
                self.sync_db.clear_all_synced_calls()

            self.sync_db.set_setting(SETTING_CALENDAR_ID, calendar_id)
        except Exception as e:
            logger.warning(f"Failed to check calendar ID: {e}")

        # Determine the 'since' date
        if since is None:
            since = self._get_default_since()
            if since:
                logger.info(f"First sync: limiting to calls since {since.date()}")

        # Get already synced call IDs for efficient filtering
        try:
            synced_ids = self.sync_db.get_synced_call_ids()
            logger.info(f"Found {len(synced_ids)} previously synced calls")
        except Exception as e:
            logger.error(f"Failed to get synced call IDs: {e}")
            return SyncResult(
                success=False,
                calls_synced=0,
                calls_skipped=0,
                errors=[f"Failed to get synced call IDs: {e}"],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # Get calls from the call database
        try:
            all_calls = list(
                self.call_db.get_calls(
                    since=since,
                    answered_only=answered_only,
                )
            )
            logger.info(f"Found {len(all_calls)} calls in database")
        except PermissionError as e:
            logger.error(f"Permission error: {e}")
            return SyncResult(
                success=False,
                calls_synced=0,
                calls_skipped=0,
                errors=[str(e)],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.error(f"Failed to get calls: {e}")
            return SyncResult(
                success=False,
                calls_synced=0,
                calls_skipped=0,
                errors=[f"Failed to get calls: {e}"],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # Filter out already synced calls AND deduplicate within current batch
        seen = set()
        calls_to_sync = []
        for c in all_calls:
            if c.unique_id not in synced_ids and c.unique_id not in seen:
                seen.add(c.unique_id)
                calls_to_sync.append(c)
        calls_skipped = len(all_calls) - len(calls_to_sync)
        logger.info(f"Calls to sync: {len(calls_to_sync)}, skipped: {calls_skipped}")

        if not calls_to_sync:
            # Mark initial sync as done even if no calls to sync
            self.sync_db.set_setting(SETTING_INITIAL_SYNC_DONE, "true")
            return SyncResult(
                success=True,
                calls_synced=0,
                calls_skipped=calls_skipped,
                errors=[],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        if dry_run:
            logger.info(f"[DRY RUN] Would sync {len(calls_to_sync)} calls")
            return SyncResult(
                success=True,
                calls_synced=len(calls_to_sync),
                calls_skipped=calls_skipped,
                errors=[],
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # Sync calls - use batch API for multiple calls
        if use_batch and len(calls_to_sync) > 1:
            # Use batch API
            results = self.calendar.create_events_batch(calls_to_sync, on_progress)

            for call_id, event_id, error in results:
                if event_id:
                    self.sync_db.mark_call_synced(call_id, event_id)
                    calls_synced += 1
                else:
                    errors.append(f"Failed to sync call {call_id}: {error}")
        else:
            # Single call or batch disabled - use individual requests
            for i, call in enumerate(calls_to_sync):
                try:
                    event_id = self.calendar.create_event_from_call(call)
                    self.sync_db.mark_call_synced(call.unique_id, event_id)
                    calls_synced += 1
                    logger.info(
                        f"Synced call {call.unique_id}: {call.display_name} "
                        f"({call.direction}, {call.duration_formatted})"
                    )
                except GoogleCalendarError as e:
                    error_msg = f"Failed to sync call {call.unique_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Unexpected error syncing call {call.unique_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

                if on_progress:
                    on_progress(i + 1, len(calls_to_sync))

        # Mark initial sync as done
        self.sync_db.set_setting(SETTING_INITIAL_SYNC_DONE, "true")

        finished_at = datetime.now(timezone.utc)
        success = len(errors) == 0

        result = SyncResult(
            success=success,
            calls_synced=calls_synced,
            calls_skipped=calls_skipped,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
        )

        logger.info(str(result))
        return result

    def get_sync_status(self) -> dict:
        """Get the current sync status.

        Returns:
            Dictionary with sync status information.
        """
        status = {
            "call_db_accessible": self.call_db.is_readable(),
            "google_authenticated": self.calendar.is_authenticated,
            "synced_calls_count": 0,
            "total_calls_count": 0,
        }

        try:
            self.sync_db.initialize()
            status["synced_calls_count"] = self.sync_db.get_synced_call_count()
        except Exception:
            pass

        try:
            if self.call_db.is_readable():
                status["total_calls_count"] = self.call_db.get_total_call_count()
        except Exception:
            pass

        return status


def main() -> int:
    """Main entry point for the sync service.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Sync macOS calls to Google Calendar")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually create events"
    )
    parser.add_argument(
        "--all-calls",
        action="store_true",
        help="Include missed/unanswered calls (default: answered only)",
    )
    parser.add_argument(
        "--all-history",
        action="store_true",
        help="Sync all call history (default: last 30 days for first sync)",
    )
    parser.add_argument(
        "--no-batch",
        action="store_true",
        help="Disable batch API (slower, but useful for debugging)",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    logger.info("Starting sync service")

    service = SyncService()

    # If user wants all history, set that preference
    if args.all_history:
        service.set_sync_all_history(True)

    result = service.sync(
        answered_only=not args.all_calls,
        dry_run=args.dry_run,
        use_batch=not args.no_batch,
    )

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())

"""Read macOS call history from the system database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

# Apple's reference date: January 1, 2001 00:00:00 UTC
APPLE_EPOCH_OFFSET = 978307200

# Default location of the call history database
DEFAULT_CALL_DB_PATH = Path.home() / "Library/Application Support/CallHistoryDB/CallHistory.storedata"


@dataclass
class CallRecord:
    """Represents a single call record from the database."""

    unique_id: str
    phone_number: str
    contact_name: Optional[str]
    timestamp: datetime
    duration_seconds: int
    is_answered: bool
    is_outgoing: bool

    @property
    def direction(self) -> str:
        """Return human-readable call direction."""
        return "Outgoing" if self.is_outgoing else "Incoming"

    @property
    def duration_formatted(self) -> str:
        """Return human-readable duration."""
        if self.duration_seconds == 0:
            return "0 seconds"

        minutes, seconds = divmod(self.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

        return " ".join(parts)

    @property
    def display_name(self) -> str:
        """Return the best available name for display."""
        return self.contact_name or self.phone_number or "Unknown"


def apple_timestamp_to_datetime(apple_timestamp: float) -> datetime:
    """Convert Apple Core Data timestamp to Python datetime."""
    unix_timestamp = apple_timestamp + APPLE_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)


def datetime_to_apple_timestamp(dt: datetime) -> float:
    """Convert Python datetime to Apple Core Data timestamp."""
    return dt.timestamp() - APPLE_EPOCH_OFFSET


class CallDatabase:
    """Interface for reading the macOS call history database."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with optional custom database path.

        Args:
            db_path: Path to the call history database. Defaults to the
                     standard macOS location.
        """
        self.db_path = db_path or DEFAULT_CALL_DB_PATH

    def exists(self) -> bool:
        """Check if the call database exists."""
        return self.db_path.exists()

    def is_readable(self) -> bool:
        """Check if the call database can be read.

        This will fail if Full Disk Access is not granted.
        """
        if not self.exists():
            return False

        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                conn.execute("SELECT 1 FROM ZCALLRECORD LIMIT 1")
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return False

    def get_calls(
        self,
        since: Optional[datetime] = None,
        answered_only: bool = True,
        min_age_seconds: int = 120,
    ) -> Iterator[CallRecord]:
        """Retrieve call records from the database.

        Args:
            since: Only return calls after this timestamp.
            answered_only: If True, only return answered calls.
            min_age_seconds: Minimum age of calls to return (to avoid
                            in-progress calls). Default is 2 minutes.

        Yields:
            CallRecord objects for matching calls.

        Raises:
            PermissionError: If Full Disk Access is not granted.
            FileNotFoundError: If the database doesn't exist.
        """
        if not self.exists():
            raise FileNotFoundError(f"Call database not found: {self.db_path}")

        # Calculate the maximum timestamp for calls (to exclude in-progress)
        cutoff_time = datetime.now(timezone.utc).timestamp() - min_age_seconds
        max_apple_timestamp = cutoff_time - APPLE_EPOCH_OFFSET

        # Build the query
        query = """
            SELECT
                ZUNIQUE_ID,
                ZADDRESS,
                ZNAME,
                ZDATE,
                ZDURATION,
                ZANSWERED,
                ZORIGINATED
            FROM ZCALLRECORD
            WHERE ZDATE < ?
        """
        params: list = [max_apple_timestamp]

        if since is not None:
            min_apple_timestamp = datetime_to_apple_timestamp(since)
            query += " AND ZDATE >= ?"
            params.append(min_apple_timestamp)

        if answered_only:
            # For incoming calls, ZANSWERED=1 means the user picked up
            # For outgoing calls, ZANSWERED is always 0, so we use duration as indicator
            # that the other person picked up (duration > 5 seconds = likely connected,
            # shorter durations are usually just ringing/voicemail)
            query += " AND (ZANSWERED = 1 OR (ZORIGINATED = 1 AND ZDURATION > 5))"

        query += " GROUP BY ZUNIQUE_ID ORDER BY ZDATE ASC"

        try:
            # Open in read-only mode
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)

                for row in cursor:
                    yield CallRecord(
                        unique_id=row["ZUNIQUE_ID"],
                        phone_number=row["ZADDRESS"] or "",
                        contact_name=row["ZNAME"],
                        timestamp=apple_timestamp_to_datetime(row["ZDATE"]),
                        duration_seconds=int(row["ZDURATION"] or 0),
                        is_answered=bool(row["ZANSWERED"]),
                        is_outgoing=bool(row["ZORIGINATED"]),
                    )
        except sqlite3.OperationalError as e:
            if "unable to open database" in str(e).lower():
                raise PermissionError(
                    "Cannot read call history. Full Disk Access permission is required."
                ) from e
            raise

    def get_call_by_unique_id(self, unique_id: str) -> Optional[CallRecord]:
        """Retrieve a specific call by its unique ID.

        Args:
            unique_id: The ZUNIQUE_ID of the call.

        Returns:
            CallRecord if found, None otherwise.
        """
        query = """
            SELECT
                ZUNIQUE_ID,
                ZADDRESS,
                ZNAME,
                ZDATE,
                ZDURATION,
                ZANSWERED,
                ZORIGINATED
            FROM ZCALLRECORD
            WHERE ZUNIQUE_ID = ?
        """

        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, [unique_id])
                row = cursor.fetchone()

                if row is None:
                    return None

                return CallRecord(
                    unique_id=row["ZUNIQUE_ID"],
                    phone_number=row["ZADDRESS"] or "",
                    contact_name=row["ZNAME"],
                    timestamp=apple_timestamp_to_datetime(row["ZDATE"]),
                    duration_seconds=int(row["ZDURATION"] or 0),
                    is_answered=bool(row["ZANSWERED"]),
                    is_outgoing=bool(row["ZORIGINATED"]),
                )
        except sqlite3.OperationalError as e:
            if "unable to open database" in str(e).lower():
                raise PermissionError(
                    "Cannot read call history. Full Disk Access permission is required."
                ) from e
            raise

    def get_total_call_count(self) -> int:
        """Get the total number of calls in the database."""
        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM ZCALLRECORD")
                return cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            if "unable to open database" in str(e).lower():
                raise PermissionError(
                    "Cannot read call history. Full Disk Access permission is required."
                ) from e
            raise

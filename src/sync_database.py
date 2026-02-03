"""Local SQLite database for tracking synced calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

# Default location for the sync database
DEFAULT_SYNC_DB_PATH = (
    Path.home() / "Library/Application Support/CallTrackingCalendar/sync.db"
)


@dataclass
class SyncedCall:
    """Represents a synced call record."""

    call_unique_id: str
    google_event_id: str
    synced_at: datetime


class SyncDatabase:
    """Interface for the local sync tracking database."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with optional custom database path.

        Args:
            db_path: Path to the sync database. Defaults to the standard
                     application support location.
        """
        self.db_path = db_path or DEFAULT_SYNC_DB_PATH

    def initialize(self) -> None:
        """Create the database and tables if they don't exist."""
        # Ensure the parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS synced_calls (
                    call_unique_id TEXT PRIMARY KEY,
                    google_event_id TEXT NOT NULL,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Create index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_synced_calls_event_id
                ON synced_calls(google_event_id)
            """)

            conn.commit()

    def is_call_synced(self, call_unique_id: str) -> bool:
        """Check if a call has already been synced.

        Args:
            call_unique_id: The unique ID of the call.

        Returns:
            True if the call has been synced, False otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM synced_calls WHERE call_unique_id = ?",
                [call_unique_id],
            )
            return cursor.fetchone() is not None

    def get_synced_call_ids(self) -> Set[str]:
        """Get all synced call unique IDs.

        Returns:
            Set of call unique IDs that have been synced.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT call_unique_id FROM synced_calls")
            return {row[0] for row in cursor.fetchall()}

    def mark_call_synced(self, call_unique_id: str, google_event_id: str) -> None:
        """Mark a call as synced.

        Args:
            call_unique_id: The unique ID of the call.
            google_event_id: The Google Calendar event ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO synced_calls
                (call_unique_id, google_event_id, synced_at)
                VALUES (?, ?, ?)
                """,
                [call_unique_id, google_event_id, datetime.now(timezone.utc).isoformat()],
            )
            conn.commit()

    def get_synced_call(self, call_unique_id: str) -> Optional[SyncedCall]:
        """Get a synced call record.

        Args:
            call_unique_id: The unique ID of the call.

        Returns:
            SyncedCall if found, None otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM synced_calls WHERE call_unique_id = ?",
                [call_unique_id],
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return SyncedCall(
                call_unique_id=row["call_unique_id"],
                google_event_id=row["google_event_id"],
                synced_at=datetime.fromisoformat(row["synced_at"]),
            )

    def remove_synced_call(self, call_unique_id: str) -> bool:
        """Remove a synced call record.

        Args:
            call_unique_id: The unique ID of the call.

        Returns:
            True if a record was removed, False otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM synced_calls WHERE call_unique_id = ?",
                [call_unique_id],
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_synced_call_count(self) -> int:
        """Get the total number of synced calls.

        Returns:
            Number of synced calls.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM synced_calls")
            return cursor.fetchone()[0]

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value.

        Args:
            key: The setting key.
            default: Default value if setting doesn't exist.

        Returns:
            The setting value or default.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                [key],
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value.

        Args:
            key: The setting key.
            value: The setting value.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                [key, value],
            )
            conn.commit()

    def delete_setting(self, key: str) -> bool:
        """Delete a setting.

        Args:
            key: The setting key.

        Returns:
            True if a setting was deleted, False otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM settings WHERE key = ?", [key])
            conn.commit()
            return cursor.rowcount > 0

    def clear_all_synced_calls(self) -> int:
        """Clear all synced call records.

        Returns:
            Number of records deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM synced_calls")
            conn.commit()
            return cursor.rowcount

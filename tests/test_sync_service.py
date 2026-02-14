"""Tests for the sync service module."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.call_database import CallDatabase, CallRecord
from src.google_calendar import GoogleCalendar, GoogleCalendarError
from src.sync_database import SyncDatabase
from src.sync_service import SyncResult, SyncService


class TestSyncResult:
    """Tests for the SyncResult dataclass."""

    def test_success_result(self):
        """Test successful sync result."""
        started = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2024, 1, 15, 10, 0, 5, tzinfo=timezone.utc)

        result = SyncResult(
            success=True,
            calls_synced=10,
            calls_skipped=5,
            errors=[],
            started_at=started,
            finished_at=finished,
        )

        assert result.success
        assert result.calls_synced == 10
        assert result.calls_skipped == 5
        assert len(result.errors) == 0
        assert result.duration_seconds == 5.0

    def test_failed_result(self):
        """Test failed sync result."""
        started = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2024, 1, 15, 10, 0, 2, tzinfo=timezone.utc)

        result = SyncResult(
            success=False,
            calls_synced=0,
            calls_skipped=0,
            errors=["Authentication failed", "Network error"],
            started_at=started,
            finished_at=finished,
        )

        assert not result.success
        assert len(result.errors) == 2

    def test_str_representation(self):
        """Test string representation of sync result."""
        started = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2024, 1, 15, 10, 0, 3, tzinfo=timezone.utc)

        result = SyncResult(
            success=True,
            calls_synced=5,
            calls_skipped=2,
            errors=[],
            started_at=started,
            finished_at=finished,
        )

        result_str = str(result)
        assert "succeeded" in result_str
        assert "5 synced" in result_str
        assert "2 skipped" in result_str


class TestSyncService:
    """Tests for the SyncService class."""

    @pytest.fixture
    def mock_call_db(self, tmp_path: Path) -> MagicMock:
        """Create a mock call database."""
        db = MagicMock(spec=CallDatabase)
        db.exists.return_value = True
        db.is_readable.return_value = True
        db.get_calls.return_value = iter([])
        return db

    @pytest.fixture
    def sync_db(self, tmp_path: Path) -> SyncDatabase:
        """Create a real sync database for testing."""
        db = SyncDatabase(tmp_path / "sync.db")
        db.initialize()
        return db

    @pytest.fixture
    def mock_calendar(self) -> MagicMock:
        """Create a mock Google Calendar."""
        calendar = MagicMock(spec=GoogleCalendar)
        calendar.is_authenticated = True
        calendar.create_event_from_call.return_value = "event-123"
        return calendar

    @pytest.fixture
    def service(
        self, mock_call_db: MagicMock, sync_db: SyncDatabase, mock_calendar: MagicMock
    ) -> SyncService:
        """Create a sync service with mocked dependencies."""
        return SyncService(
            call_db=mock_call_db,
            sync_db=sync_db,
            calendar=mock_calendar,
        )

    def test_check_prerequisites_all_ok(self, service: SyncService):
        """Test prerequisites check when everything is OK."""
        errors = service.check_prerequisites()
        assert len(errors) == 0

    def test_check_prerequisites_no_database(
        self, mock_call_db: MagicMock, sync_db: SyncDatabase, mock_calendar: MagicMock
    ):
        """Test prerequisites check when database doesn't exist."""
        mock_call_db.exists.return_value = False

        service = SyncService(
            call_db=mock_call_db,
            sync_db=sync_db,
            calendar=mock_calendar,
        )

        errors = service.check_prerequisites()
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_check_prerequisites_no_permission(
        self, mock_call_db: MagicMock, sync_db: SyncDatabase, mock_calendar: MagicMock
    ):
        """Test prerequisites check when permission is not granted."""
        mock_call_db.is_readable.return_value = False

        service = SyncService(
            call_db=mock_call_db,
            sync_db=sync_db,
            calendar=mock_calendar,
        )

        errors = service.check_prerequisites()
        assert len(errors) == 1
        assert "Full Disk Access" in errors[0]

    def test_check_prerequisites_not_authenticated(
        self, mock_call_db: MagicMock, sync_db: SyncDatabase, mock_calendar: MagicMock
    ):
        """Test prerequisites check when not authenticated."""
        mock_calendar.is_authenticated = False

        service = SyncService(
            call_db=mock_call_db,
            sync_db=sync_db,
            calendar=mock_calendar,
        )

        errors = service.check_prerequisites()
        assert len(errors) == 1
        assert "Not authenticated" in errors[0]

    def test_sync_no_calls(self, service: SyncService, mock_call_db: MagicMock):
        """Test sync when there are no calls."""
        mock_call_db.get_calls.return_value = iter([])

        result = service.sync()

        assert result.success
        assert result.calls_synced == 0
        assert result.calls_skipped == 0

    def test_sync_with_calls(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Test sync with new calls."""
        calls = [
            CallRecord(
                unique_id="call-1",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-2",
                phone_number="+15559876543",
                contact_name="Jane",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=120,
                is_answered=True,
                is_outgoing=True,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        # Mock batch create to return success for both calls
        mock_calendar.create_events_batch.return_value = [
            ("call-1", "event-1", None),
            ("call-2", "event-2", None),
        ]

        result = service.sync()

        assert result.success
        assert result.calls_synced == 2
        assert result.calls_skipped == 0
        assert mock_calendar.create_events_batch.call_count == 1

    def test_sync_skips_already_synced(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
        sync_db: SyncDatabase,
    ):
        """Test that sync skips already synced calls."""
        # Mark a call as already synced
        sync_db.mark_call_synced("call-1", "existing-event")

        calls = [
            CallRecord(
                unique_id="call-1",  # Already synced
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-2",  # New call
                phone_number="+15559876543",
                contact_name="Jane",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=120,
                is_answered=True,
                is_outgoing=True,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        # Only one call to sync, so it uses single request (not batch)
        mock_calendar.create_event_from_call.return_value = "event-2"

        result = service.sync()

        assert result.success
        assert result.calls_synced == 1
        assert result.calls_skipped == 1

    def test_sync_dry_run(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Test sync in dry run mode."""
        calls = [
            CallRecord(
                unique_id="call-1",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)

        result = service.sync(dry_run=True)

        assert result.success
        assert result.calls_synced == 1
        # Should not actually create events
        mock_calendar.create_event_from_call.assert_not_called()

    def test_sync_handles_calendar_error(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Test sync handles calendar API errors gracefully."""
        calls = [
            CallRecord(
                unique_id="call-1",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        mock_calendar.create_event_from_call.side_effect = GoogleCalendarError(
            "API error"
        )

        result = service.sync()

        assert not result.success
        assert result.calls_synced == 0
        assert len(result.errors) == 1
        assert "API error" in result.errors[0]

    def test_sync_deduplicates_calls_with_same_unique_id(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Regression: duplicate rows with the same unique_id should produce only one event."""
        calls = [
            CallRecord(
                unique_id="call-dup",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-dup",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        mock_calendar.create_event_from_call.return_value = "event-dup"

        result = service.sync(use_batch=False)

        assert result.success
        assert result.calls_synced == 1
        mock_calendar.create_event_from_call.assert_called_once()

    def test_sync_deduplicates_keeps_first_occurrence(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Regression: when duplicates exist, the first occurrence should be kept."""
        calls = [
            CallRecord(
                unique_id="call-dup",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-dup",
                phone_number="+15551234567",
                contact_name="John",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=999,  # Different duration — should be ignored
                is_answered=True,
                is_outgoing=False,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        mock_calendar.create_event_from_call.return_value = "event-dup"

        result = service.sync(use_batch=False)

        assert result.calls_synced == 1
        synced_call = mock_calendar.create_event_from_call.call_args[0][0]
        assert synced_call.duration_seconds == 60  # First occurrence

    def test_sync_batch_deduplicates_calls(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        mock_calendar: MagicMock,
    ):
        """Regression: batch path should also deduplicate within the batch."""
        calls = [
            CallRecord(
                unique_id="call-a",
                phone_number="+15551111111",
                contact_name="Alice",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-a",
                phone_number="+15551111111",
                contact_name="Alice",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=60,
                is_answered=True,
                is_outgoing=False,
            ),
            CallRecord(
                unique_id="call-b",
                phone_number="+15552222222",
                contact_name="Bob",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=120,
                is_answered=True,
                is_outgoing=True,
            ),
        ]
        mock_call_db.get_calls.return_value = iter(calls)
        mock_calendar.create_events_batch.return_value = [
            ("call-a", "event-a", None),
            ("call-b", "event-b", None),
        ]

        result = service.sync(use_batch=True)

        assert result.success
        assert result.calls_synced == 2
        # Batch should have received exactly 2 unique calls, not 3
        batch_calls = mock_calendar.create_events_batch.call_args[0][0]
        assert len(batch_calls) == 2

    def test_get_sync_status(
        self,
        service: SyncService,
        mock_call_db: MagicMock,
        sync_db: SyncDatabase,
    ):
        """Test getting sync status."""
        sync_db.mark_call_synced("call-1", "event-1")
        sync_db.mark_call_synced("call-2", "event-2")
        mock_call_db.get_total_call_count.return_value = 10

        status = service.get_sync_status()

        assert status["call_db_accessible"] is True
        assert status["google_authenticated"] is True
        assert status["synced_calls_count"] == 2
        assert status["total_calls_count"] == 10

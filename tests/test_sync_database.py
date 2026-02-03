"""Tests for the sync database module."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.sync_database import SyncDatabase


class TestSyncDatabase:
    """Tests for the SyncDatabase class."""

    @pytest.fixture
    def sync_db(self, tmp_path: Path) -> SyncDatabase:
        """Create a sync database for testing."""
        db = SyncDatabase(tmp_path / "sync.db")
        db.initialize()
        return db

    def test_initialize_creates_tables(self, sync_db: SyncDatabase):
        """Test that initialize creates the necessary tables."""
        # If we get here without errors, tables were created
        assert sync_db.db_path.exists()

    def test_initialize_idempotent(self, sync_db: SyncDatabase):
        """Test that initialize can be called multiple times safely."""
        # Should not raise an error
        sync_db.initialize()
        sync_db.initialize()

    def test_is_call_synced_not_synced(self, sync_db: SyncDatabase):
        """Test is_call_synced returns False for unsynced call."""
        assert not sync_db.is_call_synced("call-1")

    def test_is_call_synced_after_marking(self, sync_db: SyncDatabase):
        """Test is_call_synced returns True after marking call as synced."""
        sync_db.mark_call_synced("call-1", "event-1")
        assert sync_db.is_call_synced("call-1")

    def test_mark_call_synced(self, sync_db: SyncDatabase):
        """Test marking a call as synced."""
        sync_db.mark_call_synced("call-1", "event-1")

        synced_call = sync_db.get_synced_call("call-1")
        assert synced_call is not None
        assert synced_call.call_unique_id == "call-1"
        assert synced_call.google_event_id == "event-1"

    def test_mark_call_synced_updates_existing(self, sync_db: SyncDatabase):
        """Test that marking an already synced call updates the record."""
        sync_db.mark_call_synced("call-1", "event-1")
        sync_db.mark_call_synced("call-1", "event-2")

        synced_call = sync_db.get_synced_call("call-1")
        assert synced_call is not None
        assert synced_call.google_event_id == "event-2"

    def test_get_synced_call_ids(self, sync_db: SyncDatabase):
        """Test getting all synced call IDs."""
        sync_db.mark_call_synced("call-1", "event-1")
        sync_db.mark_call_synced("call-2", "event-2")
        sync_db.mark_call_synced("call-3", "event-3")

        ids = sync_db.get_synced_call_ids()
        assert ids == {"call-1", "call-2", "call-3"}

    def test_get_synced_call_ids_empty(self, sync_db: SyncDatabase):
        """Test getting synced call IDs when none exist."""
        ids = sync_db.get_synced_call_ids()
        assert ids == set()

    def test_get_synced_call_not_found(self, sync_db: SyncDatabase):
        """Test getting a non-existent synced call."""
        result = sync_db.get_synced_call("nonexistent")
        assert result is None

    def test_remove_synced_call(self, sync_db: SyncDatabase):
        """Test removing a synced call record."""
        sync_db.mark_call_synced("call-1", "event-1")

        result = sync_db.remove_synced_call("call-1")
        assert result is True
        assert not sync_db.is_call_synced("call-1")

    def test_remove_synced_call_not_found(self, sync_db: SyncDatabase):
        """Test removing a non-existent synced call."""
        result = sync_db.remove_synced_call("nonexistent")
        assert result is False

    def test_get_synced_call_count(self, sync_db: SyncDatabase):
        """Test getting the synced call count."""
        assert sync_db.get_synced_call_count() == 0

        sync_db.mark_call_synced("call-1", "event-1")
        assert sync_db.get_synced_call_count() == 1

        sync_db.mark_call_synced("call-2", "event-2")
        assert sync_db.get_synced_call_count() == 2

    def test_clear_all_synced_calls(self, sync_db: SyncDatabase):
        """Test clearing all synced call records."""
        sync_db.mark_call_synced("call-1", "event-1")
        sync_db.mark_call_synced("call-2", "event-2")
        sync_db.mark_call_synced("call-3", "event-3")

        count = sync_db.clear_all_synced_calls()
        assert count == 3
        assert sync_db.get_synced_call_count() == 0

    def test_clear_all_synced_calls_empty(self, sync_db: SyncDatabase):
        """Test clearing when no records exist."""
        count = sync_db.clear_all_synced_calls()
        assert count == 0


class TestSettings:
    """Tests for settings functionality."""

    @pytest.fixture
    def sync_db(self, tmp_path: Path) -> SyncDatabase:
        """Create a sync database for testing."""
        db = SyncDatabase(tmp_path / "sync.db")
        db.initialize()
        return db

    def test_get_setting_not_found(self, sync_db: SyncDatabase):
        """Test getting a non-existent setting."""
        result = sync_db.get_setting("nonexistent")
        assert result is None

    def test_get_setting_with_default(self, sync_db: SyncDatabase):
        """Test getting a non-existent setting with default."""
        result = sync_db.get_setting("nonexistent", "default_value")
        assert result == "default_value"

    def test_set_and_get_setting(self, sync_db: SyncDatabase):
        """Test setting and getting a value."""
        sync_db.set_setting("key1", "value1")
        result = sync_db.get_setting("key1")
        assert result == "value1"

    def test_set_setting_updates_existing(self, sync_db: SyncDatabase):
        """Test that setting an existing key updates the value."""
        sync_db.set_setting("key1", "value1")
        sync_db.set_setting("key1", "value2")
        result = sync_db.get_setting("key1")
        assert result == "value2"

    def test_delete_setting(self, sync_db: SyncDatabase):
        """Test deleting a setting."""
        sync_db.set_setting("key1", "value1")

        result = sync_db.delete_setting("key1")
        assert result is True
        assert sync_db.get_setting("key1") is None

    def test_delete_setting_not_found(self, sync_db: SyncDatabase):
        """Test deleting a non-existent setting."""
        result = sync_db.delete_setting("nonexistent")
        assert result is False

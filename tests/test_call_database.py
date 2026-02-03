"""Tests for the call database module."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.call_database import (
    APPLE_EPOCH_OFFSET,
    CallDatabase,
    CallRecord,
    apple_timestamp_to_datetime,
    datetime_to_apple_timestamp,
)


class TestTimestampConversion:
    """Tests for timestamp conversion functions."""

    def test_apple_timestamp_to_datetime(self):
        """Test converting Apple timestamp to datetime."""
        # January 1, 2020 00:00:00 UTC
        # Unix timestamp: 1577836800
        # Apple timestamp: 1577836800 - 978307200 = 599529600
        apple_ts = 599529600.0
        expected = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = apple_timestamp_to_datetime(apple_ts)
        assert result == expected

    def test_datetime_to_apple_timestamp(self):
        """Test converting datetime to Apple timestamp."""
        dt = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expected = 599529600.0
        result = datetime_to_apple_timestamp(dt)
        assert result == expected

    def test_roundtrip_conversion(self):
        """Test that conversions are reversible."""
        original_ts = 700000000.0
        dt = apple_timestamp_to_datetime(original_ts)
        result_ts = datetime_to_apple_timestamp(dt)
        assert abs(result_ts - original_ts) < 0.001

    def test_apple_epoch_offset(self):
        """Test that the Apple epoch offset is correct."""
        # Apple epoch is January 1, 2001 00:00:00 UTC
        # Unix epoch is January 1, 1970 00:00:00 UTC
        # Difference should be 978307200 seconds
        assert APPLE_EPOCH_OFFSET == 978307200


class TestCallRecord:
    """Tests for the CallRecord dataclass."""

    def test_direction_incoming(self):
        """Test direction property for incoming calls."""
        call = CallRecord(
            unique_id="test-1",
            phone_number="+15551234567",
            contact_name="John Doe",
            timestamp=datetime.now(timezone.utc),
            duration_seconds=300,
            is_answered=True,
            is_outgoing=False,
        )
        assert call.direction == "Incoming"

    def test_direction_outgoing(self):
        """Test direction property for outgoing calls."""
        call = CallRecord(
            unique_id="test-2",
            phone_number="+15551234567",
            contact_name="John Doe",
            timestamp=datetime.now(timezone.utc),
            duration_seconds=300,
            is_answered=True,
            is_outgoing=True,
        )
        assert call.direction == "Outgoing"

    def test_duration_formatted_seconds_only(self):
        """Test duration formatting for seconds only."""
        call = CallRecord(
            unique_id="test-3",
            phone_number="+15551234567",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=45,
            is_answered=True,
            is_outgoing=False,
        )
        assert call.duration_formatted == "45 seconds"

    def test_duration_formatted_minutes_and_seconds(self):
        """Test duration formatting for minutes and seconds."""
        call = CallRecord(
            unique_id="test-4",
            phone_number="+15551234567",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=125,  # 2 minutes 5 seconds
            is_answered=True,
            is_outgoing=False,
        )
        assert call.duration_formatted == "2 minutes 5 seconds"

    def test_duration_formatted_hours_minutes_seconds(self):
        """Test duration formatting for hours, minutes, and seconds."""
        call = CallRecord(
            unique_id="test-5",
            phone_number="+15551234567",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=3725,  # 1 hour 2 minutes 5 seconds
            is_answered=True,
            is_outgoing=False,
        )
        assert call.duration_formatted == "1 hour 2 minutes 5 seconds"

    def test_duration_formatted_zero(self):
        """Test duration formatting for zero duration."""
        call = CallRecord(
            unique_id="test-6",
            phone_number="+15551234567",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=0,
            is_answered=False,
            is_outgoing=False,
        )
        assert call.duration_formatted == "0 seconds"

    def test_display_name_with_contact(self):
        """Test display name when contact name is available."""
        call = CallRecord(
            unique_id="test-7",
            phone_number="+15551234567",
            contact_name="John Doe",
            timestamp=datetime.now(timezone.utc),
            duration_seconds=60,
            is_answered=True,
            is_outgoing=False,
        )
        assert call.display_name == "John Doe"

    def test_display_name_without_contact(self):
        """Test display name when contact name is not available."""
        call = CallRecord(
            unique_id="test-8",
            phone_number="+15551234567",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=60,
            is_answered=True,
            is_outgoing=False,
        )
        assert call.display_name == "+15551234567"

    def test_display_name_unknown(self):
        """Test display name when neither contact nor number is available."""
        call = CallRecord(
            unique_id="test-9",
            phone_number="",
            contact_name=None,
            timestamp=datetime.now(timezone.utc),
            duration_seconds=60,
            is_answered=True,
            is_outgoing=False,
        )
        assert call.display_name == "Unknown"


class TestCallDatabase:
    """Tests for the CallDatabase class."""

    @pytest.fixture
    def sample_db(self, tmp_path: Path) -> Path:
        """Create a sample call history database for testing."""
        db_path = tmp_path / "CallHistory.storedata"

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE ZCALLRECORD (
                Z_PK INTEGER PRIMARY KEY,
                ZUNIQUE_ID TEXT,
                ZADDRESS TEXT,
                ZNAME TEXT,
                ZDATE REAL,
                ZDURATION REAL,
                ZANSWERED INTEGER,
                ZORIGINATED INTEGER
            )
        """)

        # Insert sample calls
        # Call 1: Answered incoming call
        conn.execute("""
            INSERT INTO ZCALLRECORD
            (Z_PK, ZUNIQUE_ID, ZADDRESS, ZNAME, ZDATE, ZDURATION, ZANSWERED, ZORIGINATED)
            VALUES (1, 'call-1', '+15551234567', 'John Doe', 700000000, 300, 1, 0)
        """)

        # Call 2: Missed incoming call
        conn.execute("""
            INSERT INTO ZCALLRECORD
            (Z_PK, ZUNIQUE_ID, ZADDRESS, ZNAME, ZDATE, ZDURATION, ZANSWERED, ZORIGINATED)
            VALUES (2, 'call-2', '+15559876543', 'Jane Smith', 700001000, 0, 0, 0)
        """)

        # Call 3: Answered outgoing call
        conn.execute("""
            INSERT INTO ZCALLRECORD
            (Z_PK, ZUNIQUE_ID, ZADDRESS, ZNAME, ZDATE, ZDURATION, ZANSWERED, ZORIGINATED)
            VALUES (3, 'call-3', '+15555555555', NULL, 700002000, 120, 1, 1)
        """)

        conn.commit()
        conn.close()

        return db_path

    def test_exists(self, sample_db: Path):
        """Test that exists() returns True for existing database."""
        db = CallDatabase(sample_db)
        assert db.exists()

    def test_not_exists(self, tmp_path: Path):
        """Test that exists() returns False for non-existing database."""
        db = CallDatabase(tmp_path / "nonexistent.db")
        assert not db.exists()

    def test_is_readable(self, sample_db: Path):
        """Test that is_readable() returns True for readable database."""
        db = CallDatabase(sample_db)
        assert db.is_readable()

    def test_get_calls_all(self, sample_db: Path):
        """Test getting all calls without filtering."""
        db = CallDatabase(sample_db)
        calls = list(db.get_calls(answered_only=False, min_age_seconds=0))

        assert len(calls) == 3

    def test_get_calls_answered_only(self, sample_db: Path):
        """Test getting only answered calls."""
        db = CallDatabase(sample_db)
        calls = list(db.get_calls(answered_only=True, min_age_seconds=0))

        assert len(calls) == 2
        assert all(call.is_answered for call in calls)

    def test_get_calls_since(self, sample_db: Path):
        """Test filtering calls by timestamp."""
        db = CallDatabase(sample_db)

        # Get calls after call-1
        since = apple_timestamp_to_datetime(700000500)
        calls = list(db.get_calls(since=since, answered_only=False, min_age_seconds=0))

        assert len(calls) == 2
        assert calls[0].unique_id == "call-2"
        assert calls[1].unique_id == "call-3"

    def test_get_call_by_unique_id(self, sample_db: Path):
        """Test getting a specific call by unique ID."""
        db = CallDatabase(sample_db)
        call = db.get_call_by_unique_id("call-1")

        assert call is not None
        assert call.unique_id == "call-1"
        assert call.contact_name == "John Doe"
        assert call.phone_number == "+15551234567"

    def test_get_call_by_unique_id_not_found(self, sample_db: Path):
        """Test getting a non-existent call."""
        db = CallDatabase(sample_db)
        call = db.get_call_by_unique_id("nonexistent")

        assert call is None

    def test_get_total_call_count(self, sample_db: Path):
        """Test getting total call count."""
        db = CallDatabase(sample_db)
        count = db.get_total_call_count()

        assert count == 3

    def test_file_not_found(self, tmp_path: Path):
        """Test that FileNotFoundError is raised for non-existent database."""
        db = CallDatabase(tmp_path / "nonexistent.db")

        with pytest.raises(FileNotFoundError):
            list(db.get_calls())

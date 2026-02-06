"""Tests for the Google Calendar module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.call_database import CallRecord
from src.google_calendar import (
    AuthenticationError,
    CalendarEvent,
    GoogleCalendar,
    GoogleCalendarError,
)


@pytest.fixture
def mock_credentials():
    """Create mock credentials."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "refresh_token"
    creds.token = "access_token"
    creds.token_uri = "https://oauth2.googleapis.com/token"
    creds.client_id = "client_id"
    creds.client_secret = "client_secret"
    creds.scopes = ["https://www.googleapis.com/auth/calendar"]
    return creds


class TestGoogleCalendar:
    """Tests for the GoogleCalendar class."""

    def test_is_authenticated_no_credentials(self):
        """Test is_authenticated returns False when no credentials."""
        with patch.object(GoogleCalendar, "_load_credentials", return_value=None):
            calendar = GoogleCalendar()
            assert not calendar.is_authenticated

    def test_is_authenticated_valid_credentials(self, mock_credentials):
        """Test is_authenticated returns True with valid credentials."""
        with patch.object(
            GoogleCalendar, "_load_credentials", return_value=mock_credentials
        ):
            calendar = GoogleCalendar()
            assert calendar.is_authenticated

    def test_is_authenticated_invalid_credentials(self, mock_credentials):
        """Test is_authenticated returns False with invalid credentials."""
        mock_credentials.valid = False
        with patch.object(
            GoogleCalendar, "_load_credentials", return_value=mock_credentials
        ):
            calendar = GoogleCalendar()
            assert not calendar.is_authenticated


class TestCallRecordToEvent:
    """Tests for converting CallRecord to calendar event."""

    @pytest.fixture
    def sample_call(self) -> CallRecord:
        """Create a sample call record."""
        return CallRecord(
            unique_id="test-call-1",
            phone_number="+15551234567",
            contact_name="John Doe",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration_seconds=300,  # 5 minutes
            is_answered=True,
            is_outgoing=False,
        )

    @pytest.fixture
    def mock_calendar(self, mock_credentials):
        """Create a GoogleCalendar with mocked service."""
        with patch.object(
            GoogleCalendar, "_load_credentials", return_value=mock_credentials
        ):
            calendar = GoogleCalendar()

            # Mock the service
            mock_service = MagicMock()
            mock_service.calendarList().list().execute.return_value = {
                "items": [{"id": "calendar-123", "summary": "Call Tracking"}]
            }
            mock_service.events().insert().execute.return_value = {
                "id": "event-123",
                "summary": "Call with John Doe",
            }

            with patch.object(calendar, "_get_service", return_value=mock_service):
                calendar._service = mock_service
                yield calendar

    def test_create_event_from_call_summary(self, mock_calendar, sample_call):
        """Test that event summary is formatted correctly."""
        mock_calendar.create_event_from_call(sample_call)

        # Get the event body that was passed to insert
        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        # ↓ for incoming, 5 min duration
        assert event_body["summary"] == "↓ John Doe [5min]"

    def test_create_event_from_call_times(self, mock_calendar, sample_call):
        """Test that event times are set correctly."""
        mock_calendar.create_event_from_call(sample_call)

        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        # Start time should be the call timestamp
        assert event_body["start"]["dateTime"] == "2024-01-15T10:30:00+00:00"

        # End time should be start + duration
        assert event_body["end"]["dateTime"] == "2024-01-15T10:35:00+00:00"

    def test_create_event_from_call_description(self, mock_calendar, sample_call):
        """Test that event description contains call details."""
        mock_calendar.create_event_from_call(sample_call)

        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        description = event_body["description"]
        assert "Direction: Incoming" in description
        assert "Duration: 5 minutes" in description
        assert "Number: +15551234567" in description
        # "Answered" is not included since we only sync answered calls
        assert "Answered" not in description

    def test_create_event_from_call_outgoing(self, mock_calendar):
        """Test event description and summary for outgoing call."""
        call = CallRecord(
            unique_id="test-call-2",
            phone_number="+15551234567",
            contact_name="Jane Smith",
            timestamp=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            duration_seconds=60,
            is_answered=True,
            is_outgoing=True,
        )

        mock_calendar.create_event_from_call(call)

        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        assert "Direction: Outgoing" in event_body["description"]
        # ↑ for outgoing
        assert event_body["summary"] == "↑ Jane Smith [1min]"

    def test_create_event_from_call_no_contact_name(self, mock_calendar):
        """Test event summary when no contact name is available."""
        call = CallRecord(
            unique_id="test-call-3",
            phone_number="+15559876543",
            contact_name=None,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            duration_seconds=120,
            is_answered=True,
            is_outgoing=False,
        )

        mock_calendar.create_event_from_call(call)

        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        # ↓ for incoming, 2 min duration
        assert event_body["summary"] == "↓ +15559876543 [2min]"

    def test_create_event_minimum_duration(self, mock_calendar):
        """Test that short calls have minimum 1 minute duration for visibility."""
        call = CallRecord(
            unique_id="test-call-4",
            phone_number="+15551234567",
            contact_name="Quick Call",
            timestamp=datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc),
            duration_seconds=5,  # Very short call
            is_answered=True,
            is_outgoing=False,
        )

        mock_calendar.create_event_from_call(call)

        call_args = mock_calendar._service.events().insert.call_args
        event_body = call_args.kwargs.get("body") or call_args[1].get("body")

        # Should be at least 1 minute for visibility
        start = datetime.fromisoformat(event_body["start"]["dateTime"])
        end = datetime.fromisoformat(event_body["end"]["dateTime"])
        duration = (end - start).total_seconds()

        assert duration >= 60


class TestCalendarEvent:
    """Tests for the CalendarEvent dataclass."""

    def test_calendar_event_creation(self):
        """Test creating a CalendarEvent."""
        event = CalendarEvent(
            event_id="event-123",
            summary="Test Event",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            description="Test description",
        )

        assert event.event_id == "event-123"
        assert event.summary == "Test Event"
        assert event.description == "Test description"

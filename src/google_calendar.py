"""Google Calendar API integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .call_database import CallRecord

logger = logging.getLogger(__name__)

# OAuth scopes required for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Keyring service name for storing credentials
KEYRING_SERVICE = "CallTrackingCalendar"
KEYRING_USERNAME = "google_oauth"

# Calendar name
CALENDAR_NAME = "Call Tracking"

# Default path for OAuth client credentials
DEFAULT_CREDENTIALS_PATH = Path(__file__).parent.parent / "resources" / "credentials.json"


@dataclass
class CalendarEvent:
    """Represents a calendar event."""

    event_id: str
    summary: str
    start: datetime
    end: datetime
    description: str


class GoogleCalendarError(Exception):
    """Base exception for Google Calendar errors."""

    pass


class AuthenticationError(GoogleCalendarError):
    """Raised when authentication fails."""

    pass


class CalendarNotFoundError(GoogleCalendarError):
    """Raised when the calendar is not found."""

    pass


class GoogleCalendar:
    """Interface for Google Calendar API."""

    def __init__(self, credentials_path: Optional[Path] = None):
        """Initialize with optional custom credentials path.

        Args:
            credentials_path: Path to the OAuth client credentials JSON file.
        """
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self._credentials: Optional[Credentials] = None
        self._service = None
        self._calendar_id: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        creds = self._load_credentials()
        return creds is not None and creds.valid

    def _load_credentials(self) -> Optional[Credentials]:
        """Load credentials from keyring."""
        try:
            creds_json = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if creds_json is None:
                return None

            creds_data = json.loads(creds_json)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

            # Refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._save_credentials(creds)

            return creds
        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")
            return None

    def _save_credentials(self, creds: Credentials) -> None:
        """Save credentials to keyring."""
        creds_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "scopes": list(creds.scopes or []),
        }
        # Only include client_secret if present (not needed for PKCE/Desktop apps)
        if creds.client_secret:
            creds_data["client_secret"] = creds.client_secret
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(creds_data))

    def authenticate(self, open_browser: bool = True) -> bool:
        """Perform OAuth authentication flow.

        Args:
            open_browser: Whether to open the browser automatically.

        Returns:
            True if authentication succeeded, False otherwise.

        Raises:
            FileNotFoundError: If credentials.json doesn't exist.
        """
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth credentials file not found: {self.credentials_path}\n"
                "Please download credentials.json from Google Cloud Console."
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )

            # Use loopback IP for OAuth callback
            creds = flow.run_local_server(
                port=0,  # Use any available port
                open_browser=open_browser,
                success_message="Authentication successful! You can close this window.",
            )

            self._save_credentials(creds)
            self._credentials = creds
            self._service = None  # Reset service to use new credentials
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Authentication failed: {e}") from e

    def logout(self) -> None:
        """Remove stored credentials."""
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass  # Already deleted or doesn't exist
        self._credentials = None
        self._service = None
        self._calendar_id = None

    def _get_service(self):
        """Get the Google Calendar API service."""
        if self._service is not None:
            return self._service

        creds = self._load_credentials()
        if creds is None:
            raise AuthenticationError("Not authenticated. Please call authenticate() first.")

        self._credentials = creds
        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def get_or_create_calendar(self) -> str:
        """Get or create the Call Tracking calendar.

        Returns:
            The calendar ID.
        """
        if self._calendar_id is not None:
            return self._calendar_id

        service = self._get_service()

        # First, try to find existing calendar
        try:
            calendar_list = service.calendarList().list().execute()
            for calendar in calendar_list.get("items", []):
                if calendar["summary"] == CALENDAR_NAME:
                    self._calendar_id = calendar["id"]
                    logger.info(f"Found existing calendar: {CALENDAR_NAME}")
                    return self._calendar_id
        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            raise GoogleCalendarError(f"Failed to list calendars: {e}") from e

        # Create new calendar
        try:
            calendar = {
                "summary": CALENDAR_NAME,
                "description": "Automatically synced call history from macOS",
                "timeZone": "UTC",
            }
            created = service.calendars().insert(body=calendar).execute()
            self._calendar_id = created["id"]
            logger.info(f"Created new calendar: {CALENDAR_NAME}")
            return self._calendar_id
        except HttpError as e:
            logger.error(f"Failed to create calendar: {e}")
            raise GoogleCalendarError(f"Failed to create calendar: {e}") from e

    def create_event_from_call(self, call: CallRecord) -> str:
        """Create a calendar event from a call record.

        Args:
            call: The call record to create an event for.

        Returns:
            The created event ID.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        # Build event summary
        summary = f"Call with {call.display_name}"

        # Calculate end time
        duration = max(call.duration_seconds, 60)  # Minimum 1 minute for visibility
        end_time = call.timestamp + timedelta(seconds=duration)

        # Build description
        description_parts = [
            f"Direction: {call.direction}",
            f"Duration: {call.duration_formatted}",
            f"Answered: {'Yes' if call.is_answered else 'No'}",
        ]
        if call.phone_number:
            description_parts.append(f"Number: {call.phone_number}")

        description = "\n".join(description_parts)

        # Create event
        event: Dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": call.timestamp.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            },
            # Store call unique ID in extended properties for reference
            "extendedProperties": {
                "private": {
                    "callUniqueId": call.unique_id,
                }
            },
        }

        try:
            created = (
                service.events()
                .insert(calendarId=calendar_id, body=event)
                .execute()
            )
            logger.info(f"Created event for call {call.unique_id}: {created['id']}")
            return created["id"]
        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            raise GoogleCalendarError(f"Failed to create event: {e}") from e

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event.

        Args:
            event_id: The event ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info(f"Deleted event: {event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                return False
            logger.error(f"Failed to delete event: {e}")
            raise GoogleCalendarError(f"Failed to delete event: {e}") from e

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Get a calendar event by ID.

        Args:
            event_id: The event ID.

        Returns:
            CalendarEvent if found, None otherwise.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        try:
            event = (
                service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            )
            return CalendarEvent(
                event_id=event["id"],
                summary=event.get("summary", ""),
                start=datetime.fromisoformat(
                    event["start"].get("dateTime", event["start"].get("date"))
                ),
                end=datetime.fromisoformat(
                    event["end"].get("dateTime", event["end"].get("date"))
                ),
                description=event.get("description", ""),
            )
        except HttpError as e:
            if e.resp.status == 404:
                return None
            logger.error(f"Failed to get event: {e}")
            raise GoogleCalendarError(f"Failed to get event: {e}") from e

    def list_events(
        self,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 100,
    ) -> List[CalendarEvent]:
        """List calendar events.

        Args:
            time_min: Minimum time for events.
            time_max: Maximum time for events.
            max_results: Maximum number of events to return.

        Returns:
            List of calendar events.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        params: Dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if time_min:
            params["timeMin"] = time_min.isoformat()
        if time_max:
            params["timeMax"] = time_max.isoformat()

        try:
            result = service.events().list(**params).execute()
            events = []
            for event in result.get("items", []):
                events.append(
                    CalendarEvent(
                        event_id=event["id"],
                        summary=event.get("summary", ""),
                        start=datetime.fromisoformat(
                            event["start"].get("dateTime", event["start"].get("date"))
                        ),
                        end=datetime.fromisoformat(
                            event["end"].get("dateTime", event["end"].get("date"))
                        ),
                        description=event.get("description", ""),
                    )
                )
            return events
        except HttpError as e:
            logger.error(f"Failed to list events: {e}")
            raise GoogleCalendarError(f"Failed to list events: {e}") from e

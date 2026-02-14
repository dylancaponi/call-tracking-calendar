"""Google Calendar API integration."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

from .call_database import CallRecord

try:
    from .contacts import get_contact_name, preload_contacts
    CONTACTS_AVAILABLE = True
except Exception:
    CONTACTS_AVAILABLE = False

    def get_contact_name(phone_number):
        return None

    def preload_contacts(phone_numbers):
        return {num: None for num in phone_numbers}

# Maximum events per batch request (Google's limit is 50)
BATCH_SIZE = 50

logger = logging.getLogger(__name__)

# OAuth scopes required for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Keyring service name for storing credentials
KEYRING_SERVICE = "CallTrackingCalendar"
KEYRING_USERNAME = "google_oauth"

# Default calendar name
DEFAULT_CALENDAR_NAME = "Call Tracking"

# Default path for OAuth client credentials
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle — resources are in _MEIPASS
    DEFAULT_CREDENTIALS_PATH = Path(sys._MEIPASS) / "resources" / "credentials.json"
else:
    DEFAULT_CREDENTIALS_PATH = Path(__file__).parent.parent / "resources" / "credentials.json"

# Settings keys
SETTINGS_CALENDAR_NAME = "calendar_name"


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

    def __init__(self, credentials_path: Optional[Path] = None, calendar_name: Optional[str] = None):
        """Initialize with optional custom credentials path.

        Args:
            credentials_path: Path to the OAuth client credentials JSON file.
            calendar_name: Custom calendar name (defaults to "Call Tracking").
        """
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self._credentials: Optional[Credentials] = None
        self._service = None
        self._calendar_id: Optional[str] = None
        self._calendar_name = calendar_name or self._load_calendar_name()

    def _load_calendar_name(self) -> str:
        """Load calendar name from settings or use default."""
        try:
            from .sync_database import SyncDatabase
            db = SyncDatabase()
            db.initialize()
            name = db.get_setting(SETTINGS_CALENDAR_NAME)
            return name if name else DEFAULT_CALENDAR_NAME
        except Exception:
            return DEFAULT_CALENDAR_NAME

    def get_calendar_name(self) -> str:
        """Get the current calendar name."""
        return self._calendar_name

    def set_calendar_name(self, name: str) -> None:
        """Set the calendar name.

        Args:
            name: New calendar name.
        """
        if not name or not name.strip():
            raise ValueError("Calendar name cannot be empty")
        self._calendar_name = name.strip()
        self._calendar_id = None  # Reset cached calendar ID
        try:
            from .sync_database import SyncDatabase
            db = SyncDatabase()
            db.initialize()
            db.set_setting(SETTINGS_CALENDAR_NAME, self._calendar_name)
        except Exception as e:
            logger.warning(f"Failed to save calendar name setting: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        creds = self._load_credentials()
        return creds is not None and creds.valid

    def _load_credentials(self) -> Optional[Credentials]:
        """Load credentials from keyring (cached after first read)."""
        if self._credentials is not None and self._credentials.valid:
            return self._credentials

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

            self._credentials = creds
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

        creds_json = json.dumps(creds_data)
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, creds_json)
        except Exception as e:
            # Old keychain items from previous builds may have ACLs that block
            # this signed app. Force-delete via security CLI and retry.
            logger.warning(f"Keychain write failed ({e}), clearing old entry and retrying")
            self._force_delete_keychain_item()
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, creds_json)

        self._credentials = creds

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
            # prompt='select_account' forces account chooser even if already logged in
            creds = flow.run_local_server(
                port=0,  # Use any available port
                open_browser=open_browser,
                success_message="Authentication successful! You can close this window.",
                prompt='select_account',
            )

            self._save_credentials(creds)
            self._credentials = creds
            self._service = None  # Reset service to use new credentials
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Authentication failed: {e}") from e

    def _force_delete_keychain_item(self) -> None:
        """Delete keychain item via security CLI.

        This bypasses ACL mismatches from previous builds with different
        code signing identities.
        """
        try:
            subprocess.run(
                [
                    "security", "delete-generic-password",
                    "-s", KEYRING_SERVICE,
                    "-a", KEYRING_USERNAME,
                ],
                capture_output=True,
            )
        except Exception:
            pass

    def logout(self) -> None:
        """Remove stored credentials."""
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass  # Already deleted or doesn't exist
        except Exception:
            # ACL mismatch — try security CLI fallback
            self._force_delete_keychain_item()
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

    # Marker in description to identify calendars created by this app
    CALENDAR_DESCRIPTION_MARKER = "Automatically synced call history from macOS"

    def check_calendar_name(self, name: str) -> Tuple[bool, bool]:
        """Check if a calendar with this name exists and if it's ours.

        Args:
            name: Calendar name to check.

        Returns:
            Tuple of (exists, is_ours).
            - exists: True if a calendar with this name exists
            - is_ours: True if the calendar was created by this app
        """
        service = self._get_service()

        try:
            calendar_list = service.calendarList().list().execute()
            for calendar in calendar_list.get("items", []):
                if calendar.get("summary") == name:
                    # Check if it's ours by looking at the description
                    description = calendar.get("description", "")
                    is_ours = self.CALENDAR_DESCRIPTION_MARKER in description
                    return (True, is_ours)
        except HttpError as e:
            logger.error(f"Failed to check calendar: {e}")
            raise GoogleCalendarError(f"Failed to check calendar: {e}") from e

        return (False, False)

    def get_or_create_calendar(self) -> str:
        """Get or create the Call Tracking calendar.

        Returns:
            The calendar ID.
        """
        if self._calendar_id is not None:
            return self._calendar_id

        service = self._get_service()
        calendar_name = self._calendar_name

        # First, try to find existing calendar
        try:
            calendar_list = service.calendarList().list().execute()
            for calendar in calendar_list.get("items", []):
                if calendar["summary"] == calendar_name:
                    self._calendar_id = calendar["id"]
                    logger.info(f"Found existing calendar: {calendar_name}")
                    return self._calendar_id
        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            raise GoogleCalendarError(f"Failed to list calendars: {e}") from e

        # Create new calendar
        try:
            calendar = {
                "summary": calendar_name,
                "description": self.CALENDAR_DESCRIPTION_MARKER,
                "timeZone": "UTC",
            }
            created = service.calendars().insert(body=calendar).execute()
            self._calendar_id = created["id"]
            logger.info(f"Created new calendar: {calendar_name}")
            return self._calendar_id
        except HttpError as e:
            logger.error(f"Failed to create calendar: {e}")
            raise GoogleCalendarError(f"Failed to create calendar: {e}") from e

    def get_calendar_id(self) -> str:
        """Get the current calendar ID (creates calendar if needed)."""
        return self.get_or_create_calendar()

    def create_event_from_call(
        self, call: CallRecord, contact_name: Optional[str] = None
    ) -> str:
        """Create a calendar event from a call record.

        Args:
            call: The call record to create an event for.
            contact_name: Optional pre-resolved contact name.

        Returns:
            The created event ID.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        # Build event body (includes contact name lookup)
        event = self._build_event_body(call, contact_name)

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

    def _build_event_body(
        self, call: CallRecord, contact_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a calendar event body from a call record.

        Args:
            call: The call record.
            contact_name: Optional pre-fetched contact name.

        Returns:
            Dictionary representing the event body.
        """
        # Use contact name if provided, otherwise try to look it up
        if contact_name is None:
            contact_name = get_contact_name(call.phone_number)

        # Use contact name if available, otherwise fall back to call's display_name
        display_name = contact_name or call.display_name

        # Format duration as [Xmin] or [Xh Ym] rounded to nearest minute
        dur_secs = call.duration_seconds
        total_mins = round(dur_secs / 60)
        if total_mins < 1:
            total_mins = 1  # Show at least 1min
        if total_mins >= 60:
            hours = total_mins // 60
            mins = total_mins % 60
            if mins > 0:
                duration_str = f"{hours}h {mins}m"
            else:
                duration_str = f"{hours}h"
        else:
            duration_str = f"{total_mins}min"

        # Direction indicator matching iPhone convention
        direction_icon = "↗" if call.is_outgoing else "↙"

        summary = f"{direction_icon} {display_name} [{duration_str}]"

        duration = max(call.duration_seconds, 60)
        end_time = call.timestamp + timedelta(seconds=duration)

        description_parts = [
            f"Direction: {call.direction}",
            f"Duration: {call.duration_formatted}",
        ]
        # Always include phone number in description
        if call.phone_number:
            description_parts.append(f"Number: {call.phone_number}")

        return {
            "summary": summary,
            "description": "\n".join(description_parts),
            "start": {
                "dateTime": call.timestamp.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            },
            "extendedProperties": {
                "private": {
                    "callUniqueId": call.unique_id,
                }
            },
        }

    def create_events_batch(
        self,
        calls: List[CallRecord],
        on_progress: Optional[Callable[[int, int], None]] = None,
        contact_names: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[Tuple[str, Optional[str], Optional[str]]]:
        """Create multiple calendar events in batches.

        Args:
            calls: List of call records to create events for.
            on_progress: Optional callback(completed, total) for progress updates.
            contact_names: Optional pre-resolved phone→name mapping. If not
                provided, contacts are looked up via the Contacts framework.

        Returns:
            List of tuples: (call_unique_id, event_id or None, error or None)
        """
        if not calls:
            return []

        calendar_id = self.get_or_create_calendar()
        service = self._get_service()
        results: List[Tuple[str, Optional[str], Optional[str]]] = []
        total = len(calls)

        # Use provided contact names or look them up
        if contact_names is None:
            phone_numbers = [call.phone_number for call in calls if call.phone_number]
            contact_names = preload_contacts(phone_numbers)
        logger.info(f"Preloaded {sum(1 for v in contact_names.values() if v)} contact names")

        # Process in batches
        for batch_start in range(0, total, BATCH_SIZE):
            batch_calls = calls[batch_start:batch_start + BATCH_SIZE]
            batch_results: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

            def make_callback(call_id: str):
                def callback(request_id, response, exception):
                    if exception is not None:
                        logger.error(f"Batch insert failed for {call_id}: {exception}")
                        batch_results[call_id] = (None, str(exception))
                    else:
                        batch_results[call_id] = (response["id"], None)
                return callback

            batch = service.new_batch_http_request()

            for call in batch_calls:
                contact_name = contact_names.get(call.phone_number)
                event_body = self._build_event_body(call, contact_name)
                batch.add(
                    service.events().insert(calendarId=calendar_id, body=event_body),
                    callback=make_callback(call.unique_id),
                )

            try:
                batch.execute()
            except HttpError as e:
                logger.error(f"Batch request failed: {e}")
                # Mark all in this batch as failed
                for call in batch_calls:
                    if call.unique_id not in batch_results:
                        batch_results[call.unique_id] = (None, str(e))

            # Collect results for this batch
            for call in batch_calls:
                event_id, error = batch_results.get(call.unique_id, (None, "Unknown error"))
                results.append((call.unique_id, event_id, error))

            # Progress callback
            if on_progress:
                completed = min(batch_start + BATCH_SIZE, total)
                on_progress(completed, total)

            logger.info(f"Batch progress: {len(results)}/{total} events processed")

        return results

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

    def clear_calendar(
        self, on_progress: Optional[Callable[[int, int], None]] = None
    ) -> int:
        """Delete all events from the calendar.

        Args:
            on_progress: Optional callback(deleted, total) for progress updates.

        Returns:
            Number of events deleted.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()

        deleted_count = 0
        page_token = None

        try:
            # First, count total events
            total_events = 0
            temp_token = None
            while True:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    maxResults=250,
                    pageToken=temp_token,
                    singleEvents=True,
                ).execute()
                total_events += len(events_result.get("items", []))
                temp_token = events_result.get("nextPageToken")
                if not temp_token:
                    break

            if total_events == 0:
                return 0

            logger.info(f"Clearing {total_events} events from calendar")

            # Delete events in batches
            while True:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    maxResults=50,
                    pageToken=page_token,
                    singleEvents=True,
                ).execute()

                events = events_result.get("items", [])
                if not events:
                    break

                batch = service.new_batch_http_request()
                batch_count = 0

                for event in events:
                    event_id = event["id"]
                    batch.add(
                        service.events().delete(calendarId=calendar_id, eventId=event_id)
                    )
                    batch_count += 1

                if batch_count > 0:
                    batch.execute()
                    deleted_count += batch_count

                    if on_progress:
                        on_progress(deleted_count, total_events)

                    logger.info(f"Deleted {deleted_count}/{total_events} events")

                page_token = events_result.get("nextPageToken")
                if not page_token:
                    # Continue deleting - there may be more events
                    # Check if there are any events left
                    check_result = service.events().list(
                        calendarId=calendar_id,
                        maxResults=1,
                        singleEvents=True,
                    ).execute()
                    if not check_result.get("items"):
                        break

            logger.info(f"Cleared {deleted_count} events from calendar")
            return deleted_count

        except HttpError as e:
            logger.error(f"Failed to clear calendar: {e}")
            raise GoogleCalendarError(f"Failed to clear calendar: {e}") from e

    def get_synced_call_ids(self, time_min: datetime, time_max: datetime) -> Dict[str, str]:
        """Query existing calendar events and extract callUniqueId from extendedProperties.

        Used for multi-device dedup: finds events already synced by another Mac.

        Args:
            time_min: Start of time range to query.
            time_max: End of time range to query.

        Returns:
            Dict mapping callUniqueId → googleEventId for events that have
            a callUniqueId in their extendedProperties.private.
        """
        calendar_id = self.get_or_create_calendar()
        service = self._get_service()
        result_map: Dict[str, str] = {}
        page_token = None

        try:
            while True:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    maxResults=250,
                    singleEvents=True,
                    pageToken=page_token,
                ).execute()

                for event in events_result.get("items", []):
                    ext = event.get("extendedProperties", {}).get("private", {})
                    call_id = ext.get("callUniqueId")
                    if call_id:
                        result_map[call_id] = event["id"]

                page_token = events_result.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            logger.warning(f"Failed to query existing events for dedup: {e}")
            # Non-fatal — fall back to local-only dedup

        return result_map

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

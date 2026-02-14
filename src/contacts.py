"""Contact name lookup from macOS Contacts."""

from __future__ import annotations

import logging
import platform
import re
import sqlite3
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ADDRESSBOOK_DB_PATH = Path.home() / "Library/Application Support/AddressBook/AddressBook-v22.abcddb"


def _check_contacts_available() -> Optional[str]:
    """Check which contacts backend is available.

    Returns:
        'framework' if PyObjC Contacts framework is importable,
        'addressbook_db' if AddressBook SQLite DB exists (fallback),
        or None if neither is available.
    """
    try:
        import Contacts  # noqa: F401
        return 'framework'
    except ImportError:
        logger.debug("PyObjC Contacts framework not installed")
    except Exception as e:
        logger.debug(f"Contacts framework check failed: {e}")

    # Fallback: check for AddressBook SQLite database
    if ADDRESSBOOK_DB_PATH.exists():
        logger.debug(f"Using AddressBook SQLite fallback: {ADDRESSBOOK_DB_PATH}")
        return 'addressbook_db'

    return None


_CONTACTS_BACKEND: Optional[str] = _check_contacts_available()

# Backward compat: True if any backend is available
CONTACTS_FRAMEWORK_AVAILABLE = _CONTACTS_BACKEND is not None

# Cache for contact lookups to avoid repeated queries
_contact_cache: Dict[str, Optional[str]] = {}


def normalize_phone_number(number: str) -> str:
    """Normalize a phone number to digits only."""
    return re.sub(r'\D', '', number)


def get_contact_name(phone_number: str) -> Optional[str]:
    """Look up a contact name by phone number.

    Args:
        phone_number: The phone number to look up.

    Returns:
        Contact name if found, None otherwise.
    """
    if not phone_number:
        return None

    # Check cache first
    normalized = normalize_phone_number(phone_number)
    if normalized in _contact_cache:
        return _contact_cache[normalized]

    if _CONTACTS_BACKEND == 'framework':
        name = _lookup_contact_via_framework(phone_number)
    elif _CONTACTS_BACKEND == 'addressbook_db':
        name = _lookup_contact_via_addressbook_db(phone_number)
    else:
        name = None

    _contact_cache[normalized] = name
    return name


def _lookup_contact_via_framework(phone_number: str) -> Optional[str]:
    """Look up contact using macOS Contacts framework."""
    try:
        import Contacts

        store = Contacts.CNContactStore.alloc().init()

        # Check authorization
        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )
        if status != 3:  # 3 = Authorized
            return None

        keys = [
            Contacts.CNContactGivenNameKey,
            Contacts.CNContactFamilyNameKey,
            Contacts.CNContactOrganizationNameKey,
            Contacts.CNContactPhoneNumbersKey,
        ]

        # Create phone number predicate
        cn_phone = Contacts.CNPhoneNumber.phoneNumberWithStringValue_(phone_number)
        predicate = Contacts.CNContact.predicateForContactsMatchingPhoneNumber_(cn_phone)

        contacts, error = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
            predicate, keys, None
        )

        if error or not contacts:
            return None

        contact = contacts[0]
        given = contact.givenName() or ""
        family = contact.familyName() or ""
        org = contact.organizationName() or ""

        name = f"{given} {family}".strip()
        if not name:
            name = org

        return name if name else None

    except ImportError:
        logger.debug("PyObjC Contacts framework not available")
        return None
    except Exception as e:
        logger.debug(f"Contact lookup failed: {e}")
        return None


def _lookup_contact_via_addressbook_db(phone_number: str) -> Optional[str]:
    """Look up contact name via AddressBook SQLite database (fallback for older macOS)."""
    digits = normalize_phone_number(phone_number)
    if len(digits) < 7:
        return None
    # Match on last 10 digits to handle country code differences
    match_digits = digits[-10:]

    try:
        with sqlite3.connect(f"file:{ADDRESSBOOK_DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute("""
                SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, p.ZFULLNUMBER
                FROM ZABCDRECORD r
                JOIN ZABCDPHONENUMBER p ON r.Z_PK = p.ZOWNER
            """).fetchall()

            for first, last, org, full_number in rows:
                if full_number:
                    num_digits = re.sub(r'\D', '', full_number)
                    if num_digits.endswith(match_digits):
                        name = f"{first or ''} {last or ''}".strip()
                        if not name:
                            name = org or None
                        return name if name else None
        return None
    except (sqlite3.OperationalError, OSError) as e:
        logger.debug(f"AddressBook DB lookup failed: {e}")
        return None


def _load_all_contacts_from_addressbook_db() -> Dict[str, str]:
    """Load all contacts from AddressBook DB into a digits→name lookup dict."""
    lookup: Dict[str, str] = {}
    try:
        with sqlite3.connect(f"file:{ADDRESSBOOK_DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute("""
                SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, p.ZFULLNUMBER
                FROM ZABCDRECORD r
                JOIN ZABCDPHONENUMBER p ON r.Z_PK = p.ZOWNER
            """).fetchall()

            for first, last, org, full_number in rows:
                if full_number:
                    num_digits = re.sub(r'\D', '', full_number)
                    if len(num_digits) >= 7:
                        name = f"{first or ''} {last or ''}".strip()
                        if not name:
                            name = org or ''
                        if name:
                            # Store keyed by last 10 digits for matching
                            lookup[num_digits[-10:]] = name
    except (sqlite3.OperationalError, OSError) as e:
        logger.debug(f"AddressBook DB bulk load failed: {e}")
    return lookup


def preload_contacts(phone_numbers: list[str]) -> Dict[str, Optional[str]]:
    """Preload contact names for a list of phone numbers.

    This is more efficient than looking up one at a time.

    Args:
        phone_numbers: List of phone numbers to look up.

    Returns:
        Dictionary mapping phone numbers to contact names (or None).
    """
    results = {}

    if _CONTACTS_BACKEND == 'addressbook_db':
        # Bulk load all contacts from DB, then match
        all_contacts = _load_all_contacts_from_addressbook_db()
        for phone_number in phone_numbers:
            normalized = normalize_phone_number(phone_number)
            if normalized in _contact_cache:
                results[phone_number] = _contact_cache[normalized]
                continue
            match_digits = normalized[-10:] if len(normalized) >= 7 else normalized
            name = all_contacts.get(match_digits)
            _contact_cache[normalized] = name
            results[phone_number] = name
        return results

    if _CONTACTS_BACKEND != 'framework':
        return {num: None for num in phone_numbers}

    try:
        import Contacts

        store = Contacts.CNContactStore.alloc().init()

        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )
        if status != 3:
            logger.info("Contacts access not authorized")
            return {num: None for num in phone_numbers}

        keys = [
            Contacts.CNContactGivenNameKey,
            Contacts.CNContactFamilyNameKey,
            Contacts.CNContactOrganizationNameKey,
            Contacts.CNContactPhoneNumbersKey,
        ]

        # Fetch all contacts with phone numbers
        predicate = Contacts.CNContact.predicateForContactsInContainerWithIdentifier_(None)

        # Actually, let's fetch contacts individually for each number
        for phone_number in phone_numbers:
            normalized = normalize_phone_number(phone_number)

            if normalized in _contact_cache:
                results[phone_number] = _contact_cache[normalized]
                continue

            name = _lookup_contact_via_framework(phone_number)
            _contact_cache[normalized] = name
            results[phone_number] = name

    except ImportError:
        logger.debug("PyObjC Contacts framework not available")
        return {num: None for num in phone_numbers}
    except Exception as e:
        logger.debug(f"Contact preload failed: {e}")
        return {num: None for num in phone_numbers}

    return results


def is_contacts_authorized() -> bool:
    """Check if the app has Contacts access."""
    if _CONTACTS_BACKEND == 'framework':
        try:
            import Contacts

            status = Contacts.CNContactStore.authorizationStatusForEntityType_(
                Contacts.CNEntityTypeContacts
            )
            return status == 3  # Authorized
        except ImportError:
            return False
        except Exception:
            return False

    if _CONTACTS_BACKEND == 'addressbook_db':
        try:
            with sqlite3.connect(f"file:{ADDRESSBOOK_DB_PATH}?mode=ro", uri=True) as conn:
                conn.execute("SELECT 1 FROM ZABCDRECORD LIMIT 1")
            return True
        except (sqlite3.OperationalError, OSError):
            return False

    return False


def request_contacts_access() -> bool:
    """Request access to Contacts. Returns True if granted.

    Note: This triggers the system permission dialog if status is NotDetermined.
    If previously denied, the user must grant access via System Settings.
    """
    if _CONTACTS_BACKEND == 'addressbook_db':
        # Reading the DB triggers the macOS TCC dialog on first access
        try:
            with sqlite3.connect(f"file:{ADDRESSBOOK_DB_PATH}?mode=ro", uri=True) as conn:
                conn.execute("SELECT 1 FROM ZABCDRECORD LIMIT 1")
            return True
        except (sqlite3.OperationalError, OSError):
            return False

    if _CONTACTS_BACKEND != 'framework':
        return False

    try:
        import Contacts
        import time

        store = Contacts.CNContactStore.alloc().init()

        # Check current status
        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )

        # 0=NotDetermined - we can request
        # 2=Denied - user must go to Settings
        # 3=Authorized - already have access
        if status == 3:
            return True
        if status == 2:
            return False  # Must use Settings

        # Status is NotDetermined, request access
        result = [None]

        def handler(success, error):
            result[0] = success

        store.requestAccessForEntityType_completionHandler_(
            Contacts.CNEntityTypeContacts, handler
        )

        # Wait briefly for the dialog (up to 30 seconds)
        for _ in range(300):
            if result[0] is not None:
                return result[0]
            time.sleep(0.1)

        return is_contacts_authorized()

    except ImportError:
        return False
    except Exception:
        return False


def get_contacts_authorization_status() -> str:
    """Get the current Contacts authorization status.

    Returns:
        One of: 'not_determined', 'restricted', 'denied', 'authorized', 'unavailable', 'unknown'
    """
    if _CONTACTS_BACKEND == 'addressbook_db':
        try:
            with sqlite3.connect(f"file:{ADDRESSBOOK_DB_PATH}?mode=ro", uri=True) as conn:
                conn.execute("SELECT 1 FROM ZABCDRECORD LIMIT 1")
            return 'authorized'
        except sqlite3.OperationalError:
            return 'denied'
        except OSError:
            return 'unavailable'

    if _CONTACTS_BACKEND != 'framework':
        return 'unavailable'

    try:
        import Contacts

        status = Contacts.CNContactStore.authorizationStatusForEntityType_(
            Contacts.CNEntityTypeContacts
        )
        return {
            0: 'not_determined',
            1: 'restricted',
            2: 'denied',
            3: 'authorized',
        }.get(status, 'unknown')
    except ImportError:
        return 'unavailable'
    except Exception:
        return 'unknown'


def open_contacts_settings() -> None:
    """Open System Settings to the Contacts privacy pane."""
    import subprocess
    subprocess.run([
        'open',
        'x-apple.systempreferences:com.apple.preference.security?Privacy_Contacts'
    ])

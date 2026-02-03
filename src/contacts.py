"""Contact name lookup from macOS Contacts."""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

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

    name = _lookup_contact_via_framework(phone_number)
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


def preload_contacts(phone_numbers: list[str]) -> Dict[str, Optional[str]]:
    """Preload contact names for a list of phone numbers.

    This is more efficient than looking up one at a time.

    Args:
        phone_numbers: List of phone numbers to look up.

    Returns:
        Dictionary mapping phone numbers to contact names (or None).
    """
    results = {}

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


def request_contacts_access() -> bool:
    """Request access to Contacts. Returns True if granted.

    Note: This triggers the system permission dialog if status is NotDetermined.
    If previously denied, the user must grant access via System Settings.
    """
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
        One of: 'not_determined', 'restricted', 'denied', 'authorized', 'unknown'
    """
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
        return 'unknown'
    except Exception:
        return 'unknown'


def open_contacts_settings() -> None:
    """Open System Settings to the Contacts privacy pane."""
    import subprocess
    subprocess.run([
        'open',
        'x-apple.systempreferences:com.apple.preference.security?Privacy_Contacts'
    ])

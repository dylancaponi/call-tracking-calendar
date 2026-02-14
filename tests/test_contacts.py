"""Tests for contacts module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.contacts import (
    _lookup_contact_via_framework,
    normalize_phone_number,
)


class TestNormalizePhoneNumber:
    def test_strips_non_digits(self):
        assert normalize_phone_number("+1 (310) 567-0151") == "13105670151"

    def test_already_digits(self):
        assert normalize_phone_number("13105670151") == "13105670151"

    def test_empty(self):
        assert normalize_phone_number("") == ""


def _make_mock_contacts_module():
    """Create a mock Contacts framework module with key constants."""
    mod = MagicMock()
    mod.CNContactGivenNameKey = "givenName"
    mod.CNContactFamilyNameKey = "familyName"
    mod.CNContactOrganizationNameKey = "organizationName"
    mod.CNContactPhoneNumbersKey = "phoneNumbers"
    mod.CNEntityTypeContacts = 0
    return mod


class TestLookupContactViaFramework:
    """Tests that _lookup_contact_via_framework uses correct fetch keys."""

    def test_includes_phone_numbers_key_in_fetch(self):
        """CNContactPhoneNumbersKey must be in fetch keys for phone predicate to work."""
        mock_mod = _make_mock_contacts_module()
        mock_store = MagicMock()
        mock_mod.CNContactStore.alloc().init.return_value = mock_store
        mock_mod.CNContactStore.authorizationStatusForEntityType_.return_value = 3
        mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = ([], None)

        with patch.dict(sys.modules, {"Contacts": mock_mod}):
            _lookup_contact_via_framework("+13105670151")

        call_args = mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.call_args
        keys_arg = call_args[0][1]
        assert mock_mod.CNContactPhoneNumbersKey in keys_arg

    def test_returns_name_from_contact(self):
        """Should return 'First Last' from matched contact."""
        mock_mod = _make_mock_contacts_module()
        mock_store = MagicMock()
        mock_mod.CNContactStore.alloc().init.return_value = mock_store
        mock_mod.CNContactStore.authorizationStatusForEntityType_.return_value = 3

        mock_contact = MagicMock()
        mock_contact.givenName.return_value = "John"
        mock_contact.familyName.return_value = "Doe"
        mock_contact.organizationName.return_value = ""

        mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = (
            [mock_contact], None
        )

        with patch.dict(sys.modules, {"Contacts": mock_mod}):
            result = _lookup_contact_via_framework("+13105670151")

        assert result == "John Doe"

    def test_returns_org_when_no_name(self):
        """Should fall back to organization name when given/family are empty."""
        mock_mod = _make_mock_contacts_module()
        mock_store = MagicMock()
        mock_mod.CNContactStore.alloc().init.return_value = mock_store
        mock_mod.CNContactStore.authorizationStatusForEntityType_.return_value = 3

        mock_contact = MagicMock()
        mock_contact.givenName.return_value = ""
        mock_contact.familyName.return_value = ""
        mock_contact.organizationName.return_value = "Acme Corp"

        mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = (
            [mock_contact], None
        )

        with patch.dict(sys.modules, {"Contacts": mock_mod}):
            result = _lookup_contact_via_framework("+13105670151")

        assert result == "Acme Corp"

    def test_returns_none_when_not_authorized(self):
        """Should return None when Contacts access is denied."""
        mock_mod = _make_mock_contacts_module()
        mock_store = MagicMock()
        mock_mod.CNContactStore.alloc().init.return_value = mock_store
        mock_mod.CNContactStore.authorizationStatusForEntityType_.return_value = 2  # Denied

        with patch.dict(sys.modules, {"Contacts": mock_mod}):
            result = _lookup_contact_via_framework("+13105670151")

        assert result is None

    def test_returns_none_when_no_match(self):
        """Should return None when no contact matches the phone number."""
        mock_mod = _make_mock_contacts_module()
        mock_store = MagicMock()
        mock_mod.CNContactStore.alloc().init.return_value = mock_store
        mock_mod.CNContactStore.authorizationStatusForEntityType_.return_value = 3
        mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = ([], None)

        with patch.dict(sys.modules, {"Contacts": mock_mod}):
            result = _lookup_contact_via_framework("+13105670151")

        assert result is None

    def test_returns_none_when_framework_not_importable(self):
        """Should return None when Contacts framework is not importable."""
        with patch.dict(sys.modules, {"Contacts": None}):
            result = _lookup_contact_via_framework("+13105670151")

        assert result is None

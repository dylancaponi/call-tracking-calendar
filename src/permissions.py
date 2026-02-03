"""Check and request macOS permissions."""

import subprocess
import sys
from pathlib import Path

from .call_database import CallDatabase


def check_full_disk_access() -> bool:
    """Check if the application has Full Disk Access permission.

    Returns:
        True if Full Disk Access is granted, False otherwise.
    """
    # Try to read the call history database as a permission check
    call_db = CallDatabase()
    return call_db.is_readable()


def open_full_disk_access_settings() -> bool:
    """Open the Full Disk Access settings pane.

    Returns:
        True if the settings were opened successfully, False otherwise.
    """
    try:
        # Open System Settings (macOS Ventura+) or System Preferences (older)
        subprocess.run(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            ],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        # Fallback for older macOS versions
        try:
            subprocess.run(
                [
                    "open",
                    "/System/Library/PreferencePanes/Security.prefPane",
                ],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False


def get_app_path() -> Path:
    """Get the path to the current application.

    Returns:
        Path to the application bundle or script.
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled app
        return Path(sys.executable).parent.parent.parent
    else:
        # Running as a script
        return Path(__file__).parent.parent


def get_permission_instructions() -> str:
    """Get human-readable instructions for granting Full Disk Access.

    Returns:
        Instructions string.
    """
    app_path = get_app_path()
    app_name = app_path.name if app_path.suffix == ".app" else "Terminal"

    return f"""
Full Disk Access Permission Required

This application needs Full Disk Access to read your call history.
Your call data stays on your device and is only synced to your own Google Calendar.

To grant permission:

1. Click "Open System Settings" or go to:
   System Settings → Privacy & Security → Full Disk Access

2. Click the "+" button to add an application

3. Navigate to and select: {app_name}

4. Enable the toggle next to {app_name}

5. Restart this application

Note: You may need to enter your password or use Touch ID to make changes.
"""


def check_contacts_access() -> bool:
    """Check if the application has Contacts access permission.

    This is optional - contact names may not appear without this permission.

    Returns:
        True if Contacts access is granted, False otherwise.
    """
    # Note: The call database already contains contact names if the phone
    # app has access, so we don't strictly need Contacts access ourselves.
    # This function is provided for future use if needed.
    return True


def is_running_in_terminal() -> bool:
    """Check if the application is running in a terminal.

    Returns:
        True if running in a terminal, False otherwise.
    """
    return sys.stdin.isatty()


def is_bundled_app() -> bool:
    """Check if running as a bundled macOS app.

    Returns:
        True if running as a .app bundle, False otherwise.
    """
    return getattr(sys, "frozen", False)

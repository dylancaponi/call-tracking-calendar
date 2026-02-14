"""First-run setup wizard UI."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional, Tuple

try:
    from ..contacts import (
        get_contacts_authorization_status,
        is_contacts_authorized,
        open_contacts_settings,
        request_contacts_access,
    )
    CONTACTS_AVAILABLE = True
except Exception:
    CONTACTS_AVAILABLE = False

    def is_contacts_authorized():
        return False

    def get_contacts_authorization_status():
        return 'unknown'

    def open_contacts_settings():
        import subprocess
        subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Contacts'])

    def request_contacts_access():
        return False
from ..google_calendar import GoogleCalendar, AuthenticationError
from ..launchagent import install as install_launchagent, is_installed
from ..sync_service import SyncService
from ..permissions import (
    check_full_disk_access,
    get_permission_instructions,
    open_full_disk_access_settings,
)
from ..sync_database import SyncDatabase


class SetupWizard:
    """Setup wizard for first-run configuration."""

    def __init__(self, on_complete: Optional[Callable[[], None]] = None):
        """Initialize the setup wizard.

        Args:
            on_complete: Callback when setup is complete.
        """
        self.on_complete = on_complete
        self.root: Optional[tk.Tk] = None
        self.current_step = 0
        self.steps: List[Tuple[str, Callable[[ttk.Frame], None]]] = [
            ("Welcome", self._create_welcome_step),
            ("Permissions", self._create_permissions_step),
            ("Google Account", self._create_google_step),
            ("Contacts", self._create_contacts_step),
            ("Background Sync", self._create_launchagent_step),
            ("Complete", self._create_complete_step),
        ]
        self._google_calendar: Optional[GoogleCalendar] = None
        self.sync_db = SyncDatabase()

    @property
    def google_calendar(self) -> GoogleCalendar:
        """Lazily create GoogleCalendar to avoid early keychain access."""
        if self._google_calendar is None:
            self._google_calendar = GoogleCalendar()
        return self._google_calendar

    def run(self) -> None:
        """Run the setup wizard."""
        self.root = tk.Tk()
        self.root.title("Call Tracking Calendar Setup")
        self.root.geometry("650x500")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)

        # Center the window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Show first step
        self._show_step(0)

        # Set macOS menu bar app name after window is shown
        self.root.after(100, lambda: self._set_macos_app_name("Call Tracking Calendar"))

        self.root.mainloop()

    def _clear_frame(self) -> None:
        """Clear all widgets from the main frame."""
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def _show_step(self, step: int) -> None:
        """Show the specified step."""
        self.current_step = step
        self._clear_frame()

        # Create step indicator
        step_frame = ttk.Frame(self.main_frame)
        step_frame.pack(fill=tk.X, pady=(0, 20))

        for i, (name, _) in enumerate(self.steps):
            label_text = f"● {name}" if i == step else f"○ {name}"
            label = ttk.Label(step_frame, text=label_text, font=("Helvetica", 10))
            label.pack(side=tk.LEFT, padx=5)

        # Create content frame
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Create step content
        _, create_step = self.steps[step]
        create_step(content_frame)

    def _create_welcome_step(self, parent: ttk.Frame) -> None:
        """Create the welcome step."""
        ttk.Label(
            parent,
            text="Welcome to Call Tracking Calendar",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        message = """
This application will sync your macOS call history to a Google Calendar
named "Call Tracking". Your calls will appear as calendar events, making
it easy to track your communication history.

What this app does:
• Reads your call history (times, durations, contacts)
• Creates calendar events for each answered call
• Runs in the background to keep your calendar updated

What this app does NOT do:
• Access call content or recordings
• Share your data with anyone except your own Google Calendar
• Modify or delete your call history

Click "Next" to begin setup.
        """

        ttk.Label(parent, text=message.strip(), justify=tk.LEFT).pack(
            pady=20, padx=20, fill=tk.X
        )

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT)
        ttk.Button(
            btn_frame, text="Next →", command=lambda: self._show_step(1)
        ).pack(side=tk.RIGHT)

    def _create_permissions_step(self, parent: ttk.Frame) -> None:
        """Create the permissions step."""
        ttk.Label(
            parent,
            text="Full Disk Access Required",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        has_permission = check_full_disk_access()

        if has_permission:
            status_text = "✓ Full Disk Access is granted"
            status_color = "green"
        else:
            status_text = "✗ Full Disk Access is required"
            status_color = "red"

        status_label = ttk.Label(parent, text=status_text, foreground=status_color)
        status_label.pack(pady=10)

        if not has_permission:
            instructions = get_permission_instructions()
            text_widget = tk.Text(parent, height=12, width=60, wrap=tk.WORD)
            text_widget.insert(tk.END, instructions)
            text_widget.config(state=tk.DISABLED)
            text_widget.pack(pady=10, padx=20)

            ttk.Button(
                parent,
                text="Open System Settings",
                command=open_full_disk_access_settings,
            ).pack(pady=10)

            ttk.Button(parent, text="Check Again", command=self._refresh_permissions).pack(
                pady=5
            )
        else:
            ttk.Label(
                parent,
                text="Your call history can be accessed. You can proceed to the next step.",
            ).pack(pady=20)

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(0)).pack(
            side=tk.LEFT
        )
        next_btn = ttk.Button(
            btn_frame,
            text="Next →",
            command=lambda: self._show_step(2),
            state=tk.NORMAL if has_permission else tk.DISABLED,
        )
        next_btn.pack(side=tk.RIGHT)

    def _refresh_permissions(self) -> None:
        """Refresh the permissions step."""
        self._show_step(1)

    def _create_google_step(self, parent: ttk.Frame) -> None:
        """Create the Google account step."""
        ttk.Label(
            parent,
            text="Connect Google Account",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        is_authenticated = self.google_calendar.is_authenticated

        if is_authenticated:
            status_text = "✓ Connected to Google Calendar"
            status_color = "green"
        else:
            status_text = "○ Not connected"
            status_color = "gray"

        status_label = ttk.Label(parent, text=status_text, foreground=status_color)
        status_label.pack(pady=10)

        if not is_authenticated:
            ttk.Label(
                parent,
                text=(
                    "Click the button below to sign in with your Google account.\n"
                    "A browser window will open for authentication.\n\n"
                    "Tip: When prompted for Keychain access, click 'Always Allow'\n"
                    "to store your credentials securely without repeated prompts."
                ),
                justify=tk.CENTER,
            ).pack(pady=20)

            ttk.Button(
                parent,
                text="Sign in with Google",
                command=self._authenticate_google,
            ).pack(pady=10)
        else:
            ttk.Label(
                parent,
                text=(
                    "Your Google account is connected.\n"
                    "Events will be created in the 'Call Tracking' calendar."
                ),
                justify=tk.CENTER,
            ).pack(pady=20)

            ttk.Button(
                parent, text="Disconnect", command=self._disconnect_google
            ).pack(pady=10)

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(1)).pack(
            side=tk.LEFT
        )
        next_btn = ttk.Button(
            btn_frame,
            text="Next →",
            command=lambda: self._show_step(3),  # Go to Contacts step
            state=tk.NORMAL if is_authenticated else tk.DISABLED,
        )
        next_btn.pack(side=tk.RIGHT)

    def _authenticate_google(self) -> None:
        """Perform Google authentication in a background thread."""
        # First disconnect any existing credentials to force fresh login
        self.google_calendar.logout()

        # Show info message
        messagebox.showinfo(
            "Sign in with Google",
            "A browser window will open.\n\n"
            "Please select or sign into the Google account you want to use.\n\n"
            "If prompted for Keychain access, click 'Always Allow' to avoid\n"
            "repeated password prompts."
        )

        # Run OAuth flow in background thread so UI stays responsive
        self._auth_result: Optional[tuple] = None  # (success, error)

        def _do_auth():
            try:
                self.google_calendar.authenticate()
                self._auth_result = (True, None)
            except Exception as e:
                self._auth_result = (False, e)
            if self.root:
                self.root.after(0, self._on_auth_complete)

        threading.Thread(target=_do_auth, daemon=True).start()

        # Show waiting UI with cancel button
        self._show_auth_waiting()

    def _show_auth_waiting(self) -> None:
        """Show a waiting state on the Google step while auth is in progress."""
        self._clear_frame()

        # Recreate step indicator
        step_frame = ttk.Frame(self.main_frame)
        step_frame.pack(fill=tk.X, pady=(0, 20))
        for i, (name, _) in enumerate(self.steps):
            label_text = f"● {name}" if i == self.current_step else f"○ {name}"
            label = ttk.Label(step_frame, text=label_text, font=("Helvetica", 10))
            label.pack(side=tk.LEFT, padx=5)

        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            content_frame,
            text="Connect Google Account",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        ttk.Label(
            content_frame,
            text="Waiting for Google sign-in to complete in your browser…",
            justify=tk.CENTER,
        ).pack(pady=30)

        ttk.Button(
            content_frame,
            text="Cancel Sign-in",
            command=self._cancel_auth,
        ).pack(pady=10)

    def _cancel_auth(self) -> None:
        """Cancel the in-progress auth and return to the Google step."""
        # The daemon thread will die on its own; just navigate away
        self._auth_result = None
        self._show_step(2)

    def _on_auth_complete(self) -> None:
        """Handle auth thread completion."""
        result = self._auth_result
        if result is None:
            return  # Cancelled

        success, error = result
        self._auth_result = None

        if success:
            messagebox.showinfo("Success", "Successfully connected to Google Calendar!")
            self._show_step(2)
        elif isinstance(error, FileNotFoundError):
            messagebox.showerror("Error", str(error))
            self._show_step(2)
        else:
            messagebox.showerror(
                "Authentication Failed",
                "Google sign-in was cancelled or failed. Please try again.",
            )
            self._show_step(2)

    def _disconnect_google(self) -> None:
        """Disconnect Google account."""
        self.google_calendar.logout()
        self._show_step(2)  # Refresh the step

    def _create_contacts_step(self, parent: ttk.Frame) -> None:
        """Create the contacts permission step."""
        ttk.Label(
            parent,
            text="Contacts Access (Optional)",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        status = get_contacts_authorization_status()
        is_authorized = status == 'authorized'

        if is_authorized:
            status_text = "✓ Contacts access is granted"
            status_color = "green"
        elif status == 'unavailable':
            status_text = "⚠ Contacts database not found"
            status_color = "orange"
        elif status == 'denied':
            status_text = "✗ Contacts access was denied"
            status_color = "red"
        else:
            status_text = "○ Contacts access not yet requested"
            status_color = "gray"

        status_label = ttk.Label(parent, text=status_text, foreground=status_color)
        status_label.pack(pady=10)

        if status == 'unavailable':
            ttk.Label(
                parent,
                text=(
                    "No Contacts database was found on this system.\n\n"
                    "Your calendar events will show phone numbers instead of names.\n"
                    "You can still use all other features of the app."
                ),
                justify=tk.CENTER,
            ).pack(pady=20)
        else:
            ttk.Label(
                parent,
                text=(
                    "Granting Contacts access allows the app to show contact names\n"
                    "instead of phone numbers in your calendar events.\n\n"
                    "For example: 'Call with John Smith' instead of 'Call with +1-555-123-4567'\n\n"
                    "This is optional - the app works fine without it."
                ),
                justify=tk.CENTER,
            ).pack(pady=10)

            # Note about terminal vs bundled app
            ttk.Label(
                parent,
                text=(
                    "Note: When running from Terminal/iTerm, grant access to your\n"
                    "terminal app. The bundled .app will have its own permission."
                ),
                foreground="gray",
                font=("Helvetica", 10),
                justify=tk.CENTER,
            ).pack(pady=5)

            if not is_authorized:
                if status == 'denied':
                    ttk.Label(
                        parent,
                        text="To enable, add your terminal app in System Settings > Contacts.",
                        foreground="gray",
                    ).pack(pady=5)
                    ttk.Button(
                        parent,
                        text="Open System Settings",
                        command=open_contacts_settings,
                    ).pack(pady=5)
                    ttk.Button(
                        parent,
                        text="Check Again",
                        command=lambda: self._show_step(3),
                    ).pack(pady=5)
                else:
                    ttk.Button(
                        parent,
                        text="Enable Contacts Access",
                        command=self._request_contacts,
                    ).pack(pady=10)
            else:
                ttk.Label(
                    parent,
                    text="Calendar events will show contact names when available.",
                    foreground="gray",
                ).pack(pady=10)

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(2)).pack(
            side=tk.LEFT
        )
        # Can always proceed - this step is optional
        ttk.Button(
            btn_frame,
            text="Skip" if not is_authorized else "Next →",
            command=lambda: self._show_step(4),
        ).pack(side=tk.RIGHT)

    def _request_contacts(self) -> None:
        """Request contacts access."""
        if request_contacts_access():
            messagebox.showinfo("Success", "Contacts access granted!")
        else:
            status = get_contacts_authorization_status()
            if status == 'denied':
                messagebox.showinfo(
                    "Access Denied",
                    "Contacts access was denied. You can enable it later in System Settings."
                )
            else:
                messagebox.showinfo(
                    "Access Not Granted",
                    "Contacts access was not granted. You can enable it later in System Settings."
                )
        self._show_step(3)  # Refresh the step

    def _create_launchagent_step(self, parent: ttk.Frame) -> None:
        """Create the LaunchAgent step."""
        ttk.Label(
            parent,
            text="Sync Your Calls",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        # Sync Now section
        sync_frame = ttk.LabelFrame(parent, text="Sync Now", padding="10")
        sync_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(
            sync_frame,
            text="Sync your calls to Google Calendar now.",
            justify=tk.CENTER,
        ).pack(pady=5)

        sync_btn_frame = ttk.Frame(sync_frame)
        sync_btn_frame.pack(pady=10)

        ttk.Button(
            sync_btn_frame,
            text="Sync Last 30 Days",
            command=lambda: self._sync_now(days=30),
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            sync_btn_frame,
            text="Sync Full History",
            command=lambda: self._sync_now(days=None),
        ).pack(side=tk.LEFT, padx=5)

        # Background sync section
        agent_frame = ttk.LabelFrame(parent, text="Background Sync (Optional)", padding="10")
        agent_frame.pack(fill=tk.X, padx=20, pady=10)

        agent_installed = is_installed()

        if agent_installed:
            status_text = "✓ Background sync is enabled"
            status_color = "green"
        else:
            status_text = "○ Not enabled"
            status_color = "gray"

        status_label = ttk.Label(agent_frame, text=status_text, foreground=status_color)
        status_label.pack(pady=5)

        ttk.Label(
            agent_frame,
            text="Automatically sync new calls every 5 minutes.",
            justify=tk.CENTER,
        ).pack(pady=5)

        if not agent_installed:
            ttk.Button(
                agent_frame,
                text="Enable Background Sync",
                command=self._install_launchagent,
            ).pack(pady=5)

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(3)).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_frame, text="Next →", command=lambda: self._show_step(5)).pack(
            side=tk.RIGHT
        )

    def _sync_now(self, days: Optional[int] = 30) -> None:
        """Perform an immediate sync.

        Args:
            days: Number of days to sync, or None for full history.
        """
        from datetime import datetime, timedelta, timezone

        label = f"last {days} days" if days else "full history"
        messagebox.showinfo(
            "Syncing...",
            f"Syncing your calls ({label}).\n\n"
            "This may take a moment. Click OK to start."
        )

        since = datetime.now(timezone.utc) - timedelta(days=days) if days else datetime(2000, 1, 1, tzinfo=timezone.utc)

        try:
            if self.root:
                self.root.config(cursor="wait")
                self.root.update()

            service = SyncService()
            result = service.sync(since=since)

            if self.root:
                self.root.config(cursor="")

            if result.success:
                messagebox.showinfo(
                    "Sync Complete",
                    f"Successfully synced {result.calls_synced} calls!\n"
                    f"Skipped {result.calls_skipped} already synced.\n\n"
                    f"Check your Google Calendar for the 'Call Tracking' calendar."
                )
            else:
                errors = "\n".join(result.errors[:3])  # Show first 3 errors
                messagebox.showerror(
                    "Sync Failed",
                    f"Sync completed with errors:\n{errors}"
                )
        except Exception as e:
            if self.root:
                self.root.config(cursor="")
            messagebox.showerror("Error", f"Sync failed: {e}")

    def _install_launchagent(self) -> None:
        """Install the LaunchAgent."""
        try:
            if install_launchagent():
                messagebox.showinfo("Success", "Background sync has been enabled!")
                self._show_step(4)  # Refresh the step
            else:
                messagebox.showerror("Error", "Failed to enable background sync.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def _create_complete_step(self, parent: ttk.Frame) -> None:
        """Create the completion step."""
        ttk.Label(
            parent,
            text="Setup Complete!",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        ttk.Label(
            parent,
            text="🎉",
            font=("Helvetica", 48),
        ).pack(pady=10)

        ttk.Label(
            parent,
            text=(
                "Call Tracking Calendar is now configured.\n\n"
                "Your calls will be synced to the 'Call Tracking' calendar\n"
                "in your Google account every 5 minutes.\n\n"
                "You can access preferences anytime by running this app again."
            ),
            justify=tk.CENTER,
        ).pack(pady=20)

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(4)).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_frame, text="Finish", command=self._finish).pack(side=tk.RIGHT)

    def _cancel(self) -> None:
        """Cancel the setup wizard."""
        if messagebox.askyesno(
            "Cancel Setup", "Are you sure you want to cancel setup?"
        ):
            if self.root:
                self.root.destroy()
            sys.exit(0)

    def _finish(self) -> None:
        """Finish the setup wizard."""
        # Mark setup as complete so we don't re-show the wizard
        try:
            self.sync_db.initialize()
            self.sync_db.set_setting("setup_complete", "true")
        except Exception:
            pass
        if self.root:
            self.root.destroy()
        if self.on_complete:
            self.on_complete()

    def _set_macos_app_name(self, name: str) -> None:
        """Set the macOS menu bar app name."""
        try:
            self.root.tk.call("tk", "appname", name)
        except tk.TclError:
            pass

        try:
            from AppKit import NSApplication, NSMenu, NSMenuItem
            app = NSApplication.sharedApplication()
            main_menu = app.mainMenu()
            if main_menu and main_menu.numberOfItems() > 0:
                app_menu_item = main_menu.itemAtIndex_(0)
                if app_menu_item:
                    app_menu_item.setTitle_(name)
                    submenu = app_menu_item.submenu()
                    if submenu:
                        submenu.setTitle_(name)
        except ImportError:
            pass
        except Exception:
            pass


def run_setup_wizard(on_complete: Optional[Callable[[], None]] = None) -> None:
    """Run the setup wizard.

    Args:
        on_complete: Callback when setup is complete.
    """
    wizard = SetupWizard(on_complete=on_complete)
    wizard.run()

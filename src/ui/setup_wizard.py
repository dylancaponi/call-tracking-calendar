"""First-run setup wizard UI."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional, Tuple

from ..contacts import (
    get_contacts_authorization_status,
    is_contacts_authorized,
    open_contacts_settings,
    request_contacts_access,
)
from ..google_calendar import GoogleCalendar, AuthenticationError
from ..launchagent import install as install_launchagent, is_installed
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
        self.google_calendar = GoogleCalendar()
        self.sync_db = SyncDatabase()

    def run(self) -> None:
        """Run the setup wizard."""
        self.root = tk.Tk()
        self.root.title("Call Tracking Calendar Setup")
        self.root.geometry("600x450")
        self.root.resizable(False, False)

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
            label = ttk.Label(step_frame, text=label_text)
            label.pack(side=tk.LEFT, padx=10)

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
                    "A browser window will open for authentication."
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
        """Perform Google authentication."""
        try:
            self.google_calendar.authenticate()
            messagebox.showinfo("Success", "Successfully connected to Google Calendar!")
            self._show_step(2)  # Refresh the step
        except FileNotFoundError as e:
            messagebox.showerror("Error", str(e))
        except AuthenticationError as e:
            messagebox.showerror("Authentication Failed", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

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
        elif status == 'denied':
            status_text = "✗ Contacts access was denied"
            status_color = "red"
        else:
            status_text = "○ Contacts access not yet requested"
            status_color = "gray"

        status_label = ttk.Label(parent, text=status_text, foreground=status_color)
        status_label.pack(pady=10)

        ttk.Label(
            parent,
            text=(
                "Granting Contacts access allows the app to show contact names\n"
                "instead of phone numbers in your calendar events.\n\n"
                "For example: 'Call with John Smith' instead of 'Call with +1-555-123-4567'\n\n"
                "This is optional - the app works fine without it."
            ),
            justify=tk.CENTER,
        ).pack(pady=20)

        if not is_authorized:
            if status == 'denied':
                ttk.Label(
                    parent,
                    text="To enable, open System Settings and add this app to Contacts.",
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
            text="Background Sync",
            font=("Helvetica", 18, "bold"),
        ).pack(pady=(20, 10))

        agent_installed = is_installed()

        if agent_installed:
            status_text = "✓ Background sync is enabled"
            status_color = "green"
        else:
            status_text = "○ Background sync is not enabled"
            status_color = "gray"

        status_label = ttk.Label(parent, text=status_text, foreground=status_color)
        status_label.pack(pady=10)

        ttk.Label(
            parent,
            text=(
                "Enable background sync to automatically sync new calls every 5 minutes.\n"
                "This runs silently in the background and uses minimal resources."
            ),
            justify=tk.CENTER,
        ).pack(pady=20)

        if not agent_installed:
            ttk.Button(
                parent,
                text="Enable Background Sync",
                command=self._install_launchagent,
            ).pack(pady=10)
        else:
            ttk.Label(parent, text="Background sync is already configured.").pack(
                pady=10
            )

        # Navigation buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="← Back", command=lambda: self._show_step(3)).pack(
            side=tk.LEFT
        )
        ttk.Button(btn_frame, text="Next →", command=lambda: self._show_step(5)).pack(
            side=tk.RIGHT
        )

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
        if self.root:
            self.root.destroy()
        if self.on_complete:
            self.on_complete()


def run_setup_wizard(on_complete: Optional[Callable[[], None]] = None) -> None:
    """Run the setup wizard.

    Args:
        on_complete: Callback when setup is complete.
    """
    wizard = SetupWizard(on_complete=on_complete)
    wizard.run()

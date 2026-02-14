"""Preferences and status UI."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional


class Tooltip:
    """Simple tooltip for Tkinter widgets."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tooltip_window:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            foreground="black",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Helvetica", 11),
            padx=6,
            pady=4,
        )
        label.pack()

    def _hide(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

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
from ..google_calendar import GoogleCalendar
from ..launchagent import (
    get_logs,
    get_status as get_launchagent_status,
    install as install_launchagent,
    run_now,
    uninstall as uninstall_launchagent,
)
from ..permissions import check_full_disk_access, open_full_disk_access_settings
from ..sync_database import SyncDatabase
from ..sync_service import SyncService


class PreferencesWindow:
    """Preferences and status window."""

    def __init__(self, on_close: Optional[Callable[[], None]] = None):
        """Initialize the preferences window.

        Args:
            on_close: Callback when window is closed.
        """
        self.on_close = on_close
        self.root: Optional[tk.Tk] = None
        self._google_calendar: Optional[GoogleCalendar] = None
        self.sync_db = SyncDatabase()
        self.sync_service = SyncService()

    @property
    def google_calendar(self) -> GoogleCalendar:
        """Lazily create GoogleCalendar to avoid early keychain access."""
        if self._google_calendar is None:
            self._google_calendar = GoogleCalendar()
        return self._google_calendar

    def run(self) -> None:
        """Run the preferences window."""
        self.root = tk.Tk()
        self.root.title("Call Tracking Calendar")
        self.root.geometry("500x650")
        self.root.resizable(True, True)
        self.root.minsize(500, 600)

        # Center the window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create empty tab frames (content populated after window is visible)
        self.status_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.status_frame, text="Status")

        self.settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_frame, text="Settings")

        self.logs_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.logs_frame, text="Logs")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        # Set macOS menu bar app name after window is shown
        self.root.after(100, lambda: self._set_macos_app_name("Call Tracking Calendar"))

        # Populate tabs after window is visible so keychain dialog doesn't block render
        self.root.after(200, self._populate_tabs)

        self.root.mainloop()

    def _populate_tabs(self) -> None:
        """Populate tab contents (deferred so window renders first)."""
        self._create_status_tab(self.status_frame)
        self._create_settings_tab(self.settings_frame)
        self._create_logs_tab(self.logs_frame)

    def _create_status_tab(self, parent: ttk.Frame) -> None:
        """Create the status tab content."""
        # Title
        ttk.Label(
            parent,
            text="Sync Status",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(0, 20))

        # Status info
        status = self.sync_service.get_sync_status()

        # Permissions status
        perm_frame = ttk.LabelFrame(parent, text="Permissions", padding="10")
        perm_frame.pack(fill=tk.X, pady=5)

        has_fda = check_full_disk_access()
        fda_text = "✓ Granted" if has_fda else "✗ Not Granted"
        fda_color = "green" if has_fda else "red"
        ttk.Label(perm_frame, text="Full Disk Access:").pack(side=tk.LEFT)
        ttk.Label(perm_frame, text=fda_text, foreground=fda_color).pack(side=tk.LEFT, padx=10)
        if not has_fda:
            ttk.Button(
                perm_frame, text="Grant", command=open_full_disk_access_settings
            ).pack(side=tk.RIGHT)

        # Contacts status
        contacts_frame = ttk.LabelFrame(parent, text="Contacts (Optional)", padding="10")
        contacts_frame.pack(fill=tk.X, pady=5)

        has_contacts = is_contacts_authorized()
        contacts_text = "✓ Granted" if has_contacts else "○ Not Granted"
        contacts_color = "green" if has_contacts else "gray"
        ttk.Label(contacts_frame, text="Contacts Access:").pack(side=tk.LEFT)
        ttk.Label(contacts_frame, text=contacts_text, foreground=contacts_color).pack(
            side=tk.LEFT, padx=10
        )
        if not has_contacts:
            ttk.Button(
                contacts_frame, text="Enable", command=self._enable_contacts
            ).pack(side=tk.RIGHT)

        # Google status (checked in background thread to avoid keychain dialog blocking UI)
        google_frame = ttk.LabelFrame(parent, text="Google Calendar", padding="10")
        google_frame.pack(fill=tk.X, pady=5)

        ttk.Label(google_frame, text="Status:").pack(side=tk.LEFT)
        google_status_label = ttk.Label(google_frame, text="Checking…", foreground="gray")
        google_status_label.pack(side=tk.LEFT, padx=10)

        def _check_auth():
            is_auth = self.google_calendar.is_authenticated
            if self.root:
                self.root.after(0, lambda: _update_google_status(is_auth))

        def _update_google_status(is_auth):
            auth_text = "✓ Connected" if is_auth else "✗ Not Connected"
            auth_color = "green" if is_auth else "red"
            google_status_label.config(text=auth_text, foreground=auth_color)

        threading.Thread(target=_check_auth, daemon=True).start()

        # Sync stats - custom header with info icon
        stats_header = ttk.Frame(parent)
        stats_header.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(
            stats_header, text="Sync Statistics", font=("Helvetica", 11, "bold")
        ).pack(side=tk.LEFT)
        help_label = tk.Label(
            stats_header, text="ⓘ", foreground="blue", cursor="hand2", font=("Helvetica", 11)
        )
        help_label.pack(side=tk.LEFT, padx=(5, 0))
        Tooltip(
            help_label,
            "Only connected calls are synced\n"
            "(where you or the other person picked up).\n\n"
            "Recent calls may take time to sync from\n"
            "your iPhone via iCloud. If a call is missing,\n"
            "use the Trigger iCloud Sync button to nudge it."
        )
        ttk.Button(
            stats_header, text="Trigger iCloud Sync", command=self._trigger_icloud_sync
        ).pack(side=tk.RIGHT)

        stats_frame = ttk.Frame(parent, padding="10")
        stats_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(
            stats_frame, text=f"Synced calls: {status['synced_calls_count']}"
        ).pack(anchor=tk.W)
        ttk.Label(
            stats_frame, text=f"Total calls in history: {status['total_calls_count']}"
        ).pack(anchor=tk.W)

        # LaunchAgent status
        agent_status = get_launchagent_status()
        agent_frame = ttk.LabelFrame(parent, text="Background Sync", padding="10")
        agent_frame.pack(fill=tk.X, pady=5)

        agent_text = "✓ Running" if agent_status["loaded"] else "○ Not Running"
        agent_color = "green" if agent_status["loaded"] else "gray"
        ttk.Label(agent_frame, text="Status:").pack(side=tk.LEFT)
        ttk.Label(agent_frame, text=agent_text, foreground=agent_color).pack(
            side=tk.LEFT, padx=10
        )

        # Action buttons and status
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill=tk.X, pady=(10, 5))

        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(anchor=tk.W)

        self.sync_30d_btn = ttk.Button(
            btn_frame, text="Sync Last 30 Days", command=lambda: self._sync_now(days=30)
        )
        self.sync_30d_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.sync_full_btn = ttk.Button(
            btn_frame, text="Sync Full History", command=lambda: self._sync_now(days=None)
        )
        self.sync_full_btn.pack(side=tk.LEFT)

        # Status label for sync progress
        self.status_label = ttk.Label(action_frame, text="", foreground="gray")
        self.status_label.pack(anchor=tk.W, pady=(5, 0))

    def _create_settings_tab(self, parent: ttk.Frame) -> None:
        """Create the settings tab content."""
        # Title
        ttk.Label(
            parent,
            text="Settings",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(0, 20))

        # Google account (checked in background to avoid keychain blocking UI)
        google_frame = ttk.LabelFrame(parent, text="Google Account", padding="10")
        google_frame.pack(fill=tk.X, pady=5)

        google_settings_label = ttk.Label(google_frame, text="Checking…", foreground="gray")
        google_settings_label.pack(anchor=tk.W)

        def _check_settings_auth():
            is_auth = self.google_calendar.is_authenticated
            if self.root:
                self.root.after(0, lambda: _update_settings_auth(is_auth))

        def _update_settings_auth(is_auth):
            google_settings_label.destroy()
            if is_auth:
                ttk.Label(google_frame, text="Connected to Google Calendar").pack(
                    anchor=tk.W
                )
                ttk.Button(
                    google_frame, text="Disconnect", command=self._disconnect_google
                ).pack(anchor=tk.W, pady=5)
            else:
                ttk.Label(google_frame, text="Not connected").pack(anchor=tk.W)
                ttk.Button(
                    google_frame, text="Connect", command=self._connect_google
                ).pack(anchor=tk.W, pady=5)

        threading.Thread(target=_check_settings_auth, daemon=True).start()

        # Background sync
        agent_frame = ttk.LabelFrame(parent, text="Background Sync", padding="10")
        agent_frame.pack(fill=tk.X, pady=5)

        agent_status = get_launchagent_status()

        if agent_status["installed"]:
            ttk.Label(
                agent_frame, text="Background sync is enabled (every 5 minutes)"
            ).pack(anchor=tk.W)
            ttk.Button(
                agent_frame, text="Disable", command=self._disable_background_sync
            ).pack(anchor=tk.W, pady=5)
        else:
            ttk.Label(agent_frame, text="Background sync is disabled").pack(anchor=tk.W)
            ttk.Button(
                agent_frame, text="Enable", command=self._enable_background_sync
            ).pack(anchor=tk.W, pady=5)

        # Contacts access
        contacts_frame = ttk.LabelFrame(parent, text="Contacts Access", padding="10")
        contacts_frame.pack(fill=tk.X, pady=5)

        has_contacts = is_contacts_authorized()
        if has_contacts:
            ttk.Label(
                contacts_frame,
                text="Contacts access is enabled.\nCalendar events will show contact names.",
            ).pack(anchor=tk.W)
        else:
            ttk.Label(
                contacts_frame,
                text="Enable to show contact names instead of phone numbers.",
            ).pack(anchor=tk.W)
            ttk.Button(
                contacts_frame, text="Enable Contacts Access", command=self._enable_contacts
            ).pack(anchor=tk.W, pady=5)

        # Calendar settings
        calendar_frame = ttk.LabelFrame(parent, text="Calendar", padding="10")
        calendar_frame.pack(fill=tk.X, pady=5)

        # Calendar name
        name_frame = ttk.Frame(calendar_frame)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="Calendar name:").pack(side=tk.LEFT)
        self.calendar_name_var = tk.StringVar(value=self.google_calendar.get_calendar_name())
        self.calendar_name_entry = ttk.Entry(name_frame, textvariable=self.calendar_name_var, width=25)
        self.calendar_name_entry.pack(side=tk.LEFT, padx=10)
        ttk.Button(name_frame, text="Save", command=self._save_calendar_name).pack(side=tk.LEFT)

        ttk.Label(
            calendar_frame,
            text="Note: Changing the name creates a new calendar. Existing events stay in the old calendar.",
            foreground="gray",
            font=("Helvetica", 10),
        ).pack(anchor=tk.W, pady=(5, 0))

        # Clear calendar
        clear_frame = ttk.Frame(calendar_frame)
        clear_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            clear_frame, text="Clear All Events", command=self._clear_calendar
        ).pack(side=tk.LEFT)
        ttk.Label(
            clear_frame,
            text="Delete all events from the calendar",
            foreground="gray",
        ).pack(side=tk.LEFT, padx=10)

        # Status label for settings tab operations
        self.settings_status_label = ttk.Label(calendar_frame, text="", foreground="gray")
        self.settings_status_label.pack(anchor=tk.W, pady=(10, 0))


    def _create_logs_tab(self, parent: ttk.Frame) -> None:
        """Create the logs tab content."""
        # Title
        ttk.Label(
            parent,
            text="Recent Logs",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(0, 10))

        # Log text area
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Courier", 10),
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Load logs
        self._refresh_logs()

        # Refresh button
        ttk.Button(parent, text="Refresh Logs", command=self._refresh_logs).pack(
            pady=10
        )

    def _sync_now(self, days: Optional[int] = 30) -> None:
        """Trigger an immediate sync with progress updates.

        Args:
            days: Number of days to sync, or None for full history.
        """
        from datetime import datetime, timedelta, timezone

        # Disable buttons during sync
        self.sync_30d_btn.config(state=tk.DISABLED)
        self.sync_full_btn.config(state=tk.DISABLED)

        label = f"last {days} days" if days else "full history"
        self._update_status(f"Starting sync ({label})...")

        since = datetime.now(timezone.utc) - timedelta(days=days) if days else datetime(2000, 1, 1, tzinfo=timezone.utc)

        def do_sync():
            try:
                self._update_status("Reading call history...")
                if self.root:
                    self.root.update()

                result = self.sync_service.sync(
                    since=since,
                    on_progress=self._on_sync_progress,
                )

                self._update_status(
                    f"Done: {result.calls_synced} synced, {result.calls_skipped} skipped"
                )
                messagebox.showinfo(
                    "Sync Complete",
                    f"Synced {result.calls_synced} calls.\n"
                    f"Skipped {result.calls_skipped} already synced.",
                )
            except Exception as e:
                self._update_status(f"Error: {e}")
                messagebox.showerror("Sync Failed", str(e))
            finally:
                self.sync_30d_btn.config(state=tk.NORMAL)
                self.sync_full_btn.config(state=tk.NORMAL)

        # Run sync (Tkinter doesn't have great threading, but this keeps UI responsive)
        if self.root:
            self.root.after(100, do_sync)

    def _on_sync_progress(self, completed: int, total: int) -> None:
        """Handle sync progress updates."""
        self._update_status(f"Syncing... {completed}/{total} calls")
        if self.root:
            self.root.update()

    def _update_status(self, text: str) -> None:
        """Update the status label."""
        if hasattr(self, 'status_label'):
            self.status_label.config(text=text)
            if self.root:
                self.root.update_idletasks()

    def _trigger_icloud_sync(self) -> None:
        """Open FaceTime to a number to trigger iCloud call history sync."""
        import subprocess
        subprocess.Popen(["open", "facetime://+15055034455"])

    def _refresh_status(self) -> None:
        """Refresh the status tab."""
        # Recreate the window to refresh all data
        if self.root:
            self.root.destroy()
        self.run()

    def _refresh_logs(self) -> None:
        """Refresh the logs display."""
        if hasattr(self, "log_text"):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, get_logs(100))
            self.log_text.config(state=tk.DISABLED)
            self.log_text.see(tk.END)

    def _connect_google(self) -> None:
        """Connect Google account in a background thread."""
        def _do_auth():
            try:
                self.google_calendar.authenticate()
                if self.root:
                    self.root.after(0, lambda: self._on_connect_complete(True, None))
            except Exception as e:
                if self.root:
                    self.root.after(0, lambda: self._on_connect_complete(False, e))

        threading.Thread(target=_do_auth, daemon=True).start()

    def _on_connect_complete(self, success: bool, error) -> None:
        """Handle Google auth completion."""
        if success:
            messagebox.showinfo("Success", "Successfully connected to Google Calendar!")
            self._refresh_status()
        else:
            messagebox.showerror("Error", str(error))

    def _disconnect_google(self) -> None:
        """Disconnect Google account."""
        if messagebox.askyesno(
            "Disconnect",
            "Are you sure you want to disconnect your Google account?\n"
            "Syncing will stop until you reconnect.",
        ):
            self.google_calendar.logout()
            self._refresh_status()

    def _enable_background_sync(self) -> None:
        """Enable background sync."""
        if install_launchagent():
            messagebox.showinfo("Success", "Background sync has been enabled!")
            self._refresh_status()
        else:
            messagebox.showerror("Error", "Failed to enable background sync.")

    def _disable_background_sync(self) -> None:
        """Disable background sync."""
        if messagebox.askyesno(
            "Disable",
            "Are you sure you want to disable background sync?\n"
            "Calls will no longer be synced automatically.",
        ):
            if uninstall_launchagent():
                messagebox.showinfo("Success", "Background sync has been disabled.")
                self._refresh_status()
            else:
                messagebox.showerror("Error", "Failed to disable background sync.")

    def _enable_contacts(self) -> None:
        """Enable contacts access."""
        status = get_contacts_authorization_status()

        if status == 'authorized':
            messagebox.showinfo("Already Enabled", "Contacts access is already enabled.")
            return

        if status == 'denied':
            # Must go to System Settings
            messagebox.showinfo(
                "Open Settings",
                "Contacts access was previously denied.\n"
                "Please enable it in System Settings.",
            )
            open_contacts_settings()
        else:
            # Try to request access
            if request_contacts_access():
                messagebox.showinfo("Success", "Contacts access has been enabled!")
                self._refresh_status()
            else:
                # Request didn't work, open settings
                new_status = get_contacts_authorization_status()
                if new_status == 'denied':
                    messagebox.showinfo(
                        "Access Denied",
                        "Contacts access was denied.\n"
                        "You can enable it in System Settings.",
                    )
                    open_contacts_settings()

    def _save_calendar_name(self) -> None:
        """Save the calendar name setting."""
        new_name = self.calendar_name_var.get().strip()
        if not new_name:
            messagebox.showerror("Error", "Calendar name cannot be empty.")
            return

        old_name = self.google_calendar.get_calendar_name()
        if new_name == old_name:
            messagebox.showinfo("Info", "Calendar name unchanged.")
            return

        # Check if a calendar with this name already exists
        try:
            exists, is_ours = self.google_calendar.check_calendar_name(new_name)
            if exists and not is_ours:
                messagebox.showerror(
                    "Name Already Used",
                    f"A calendar named '{new_name}' already exists in your\n"
                    "Google account and was not created by this app.\n\n"
                    "Using this name could result in accidentally deleting\n"
                    "your personal events. Please choose a different name.",
                )
                return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to check calendar: {e}")
            return

        confirm_msg = f"Change calendar from '{old_name}' to '{new_name}'?\n\n"
        if exists and is_ours:
            confirm_msg += "A Call Tracking calendar with this name already exists.\nNew calls will sync to that calendar."
        else:
            confirm_msg += "This will create a new calendar. Existing events will remain\nin the old calendar."

        if messagebox.askyesno("Change Calendar Name", confirm_msg):
            try:
                self.google_calendar.set_calendar_name(new_name)
                messagebox.showinfo(
                    "Success",
                    f"Calendar name changed to '{new_name}'.\n\n"
                    "New calls will sync to the new calendar.",
                )
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _clear_calendar(self) -> None:
        """Clear all events from the calendar with progress updates."""
        self._update_settings_status("Clearing calendar...")

        def do_clear():
            try:
                def on_progress(deleted, total):
                    self._update_settings_status(f"Deleting... {deleted}/{total} events")

                deleted = self.google_calendar.clear_calendar(on_progress=on_progress)

                # Also clear sync history so calls can be re-synced
                self._update_settings_status("Clearing sync history...")

                self.sync_db.initialize()
                self.sync_db.clear_all_synced_calls()

                self._update_settings_status(
                    f"Deleted {deleted} events. Sync history cleared."
                )
            except Exception as e:
                self._update_settings_status(f"Error: {e}")

        if self.root:
            self.root.after(100, do_clear)

    def _update_settings_status(self, text: str) -> None:
        """Update the settings tab status label."""
        if hasattr(self, 'settings_status_label'):
            self.settings_status_label.config(text=text)
            if self.root:
                self.root.update_idletasks()
                self.root.update()

    def _set_macos_app_name(self, name: str) -> None:
        """Set the macOS menu bar app name."""
        # Try Tk appname first
        try:
            self.root.tk.call("tk", "appname", name)
        except tk.TclError:
            pass

        # Use PyObjC to modify the application menu directly
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

    def _close(self) -> None:
        """Close the window."""
        if self.root:
            self.root.destroy()
        if self.on_close:
            self.on_close()


def run_preferences(on_close: Optional[Callable[[], None]] = None) -> None:
    """Run the preferences window.

    Args:
        on_close: Callback when window is closed.
    """
    window = PreferencesWindow(on_close=on_close)
    window.run()

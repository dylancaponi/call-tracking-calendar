"""Preferences and status UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

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
        self.google_calendar = GoogleCalendar()
        self.sync_db = SyncDatabase()
        self.sync_service = SyncService()

    def run(self) -> None:
        """Run the preferences window."""
        self.root = tk.Tk()
        self.root.title("Call Tracking Calendar")
        self.root.geometry("500x600")
        self.root.resizable(False, False)

        # Center the window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Status tab
        status_frame = ttk.Frame(notebook, padding="10")
        notebook.add(status_frame, text="Status")
        self._create_status_tab(status_frame)

        # Settings tab
        settings_frame = ttk.Frame(notebook, padding="10")
        notebook.add(settings_frame, text="Settings")
        self._create_settings_tab(settings_frame)

        # Logs tab
        logs_frame = ttk.Frame(notebook, padding="10")
        notebook.add(logs_frame, text="Logs")
        self._create_logs_tab(logs_frame)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.root.mainloop()

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

        # Google status
        google_frame = ttk.LabelFrame(parent, text="Google Calendar", padding="10")
        google_frame.pack(fill=tk.X, pady=5)

        is_auth = self.google_calendar.is_authenticated
        auth_text = "✓ Connected" if is_auth else "✗ Not Connected"
        auth_color = "green" if is_auth else "red"
        ttk.Label(google_frame, text="Status:").pack(side=tk.LEFT)
        ttk.Label(google_frame, text=auth_text, foreground=auth_color).pack(
            side=tk.LEFT, padx=10
        )

        # Sync stats
        stats_frame = ttk.LabelFrame(parent, text="Sync Statistics", padding="10")
        stats_frame.pack(fill=tk.X, pady=5)

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

        # Action buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="Sync Now", command=self._sync_now).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_frame, text="Refresh", command=self._refresh_status).pack(
            side=tk.LEFT, padx=5
        )

    def _create_settings_tab(self, parent: ttk.Frame) -> None:
        """Create the settings tab content."""
        # Title
        ttk.Label(
            parent,
            text="Settings",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(0, 20))

        # Google account
        google_frame = ttk.LabelFrame(parent, text="Google Account", padding="10")
        google_frame.pack(fill=tk.X, pady=5)

        is_auth = self.google_calendar.is_authenticated

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

        # Data management
        data_frame = ttk.LabelFrame(parent, text="Data Management", padding="10")
        data_frame.pack(fill=tk.X, pady=5)

        ttk.Label(
            data_frame,
            text="Clear sync history to re-sync all calls",
        ).pack(anchor=tk.W)
        ttk.Button(
            data_frame, text="Clear Sync History", command=self._clear_sync_history
        ).pack(anchor=tk.W, pady=5)

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

    def _sync_now(self) -> None:
        """Trigger an immediate sync."""
        # First try to use the LaunchAgent
        if run_now():
            messagebox.showinfo(
                "Sync Started", "Background sync has been triggered."
            )
        else:
            # Fall back to running sync directly
            try:
                result = self.sync_service.sync()
                messagebox.showinfo(
                    "Sync Complete",
                    f"Synced {result.calls_synced} calls.\n"
                    f"Skipped {result.calls_skipped} already synced.",
                )
            except Exception as e:
                messagebox.showerror("Sync Failed", str(e))

        self._refresh_status()

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
        """Connect Google account."""
        try:
            self.google_calendar.authenticate()
            messagebox.showinfo("Success", "Successfully connected to Google Calendar!")
            self._refresh_status()
        except Exception as e:
            messagebox.showerror("Error", str(e))

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

    def _clear_sync_history(self) -> None:
        """Clear sync history."""
        if messagebox.askyesno(
            "Clear History",
            "Are you sure you want to clear the sync history?\n"
            "All calls will be synced again on the next sync.",
        ):
            try:
                self.sync_db.initialize()
                count = self.sync_db.clear_all_synced_calls()
                messagebox.showinfo(
                    "Success", f"Cleared {count} synced call records."
                )
                self._refresh_status()
            except Exception as e:
                messagebox.showerror("Error", str(e))

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

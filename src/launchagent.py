"""Manage the LaunchAgent for background sync."""

import plistlib
import subprocess
import sys
from pathlib import Path

# LaunchAgent identifiers
LAUNCH_AGENT_LABEL = "com.calltracking.calendar"
LAUNCH_AGENT_FILENAME = f"{LAUNCH_AGENT_LABEL}.plist"

# Default sync interval in seconds (5 minutes)
DEFAULT_SYNC_INTERVAL = 300


def get_launch_agents_dir() -> Path:
    """Get the user's LaunchAgents directory.

    Returns:
        Path to ~/Library/LaunchAgents
    """
    return Path.home() / "Library" / "LaunchAgents"


def get_plist_path() -> Path:
    """Get the path to the LaunchAgent plist file.

    Returns:
        Path to the plist file.
    """
    return get_launch_agents_dir() / LAUNCH_AGENT_FILENAME


def get_sync_executable_path() -> Path:
    """Get the path to the sync executable.

    Returns:
        Path to the sync script/executable.
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled app - sync executable is in the bundle
        app_path = Path(sys.executable).parent.parent.parent
        return app_path / "Contents" / "MacOS" / "sync"
    else:
        # Running as a script - use the module directly
        return Path(sys.executable)


def get_sync_arguments() -> list[str]:
    """Get the arguments for running the sync service.

    Returns:
        List of command arguments.
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled app
        return [str(get_sync_executable_path())]
    else:
        # Running as a script - run the sync module
        return [
            str(get_sync_executable_path()),
            "-m",
            "src.sync_service",
        ]


def create_plist_content(
    sync_interval: int = DEFAULT_SYNC_INTERVAL,
    run_at_load: bool = True,
) -> dict:
    """Create the plist content for the LaunchAgent.

    Args:
        sync_interval: Interval between syncs in seconds.
        run_at_load: Whether to run immediately when loaded.

    Returns:
        Dictionary containing the plist content.
    """
    args = get_sync_arguments()

    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": args,
        "StartInterval": sync_interval,
        "RunAtLoad": run_at_load,
        "StandardOutPath": str(
            Path.home()
            / "Library"
            / "Logs"
            / "CallTrackingCalendar"
            / "sync.log"
        ),
        "StandardErrorPath": str(
            Path.home()
            / "Library"
            / "Logs"
            / "CallTrackingCalendar"
            / "sync.log"
        ),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }


def is_installed() -> bool:
    """Check if the LaunchAgent is installed.

    Returns:
        True if the plist file exists.
    """
    return get_plist_path().exists()


def is_loaded() -> bool:
    """Check if the LaunchAgent is currently loaded.

    Returns:
        True if the agent is loaded.
    """
    try:
        result = subprocess.run(
            ["launchctl", "list", LAUNCH_AGENT_LABEL],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def install(
    sync_interval: int = DEFAULT_SYNC_INTERVAL,
    run_at_load: bool = True,
) -> bool:
    """Install and load the LaunchAgent.

    Args:
        sync_interval: Interval between syncs in seconds.
        run_at_load: Whether to run immediately when loaded.

    Returns:
        True if installation succeeded.
    """
    # Create LaunchAgents directory if it doesn't exist
    launch_agents_dir = get_launch_agents_dir()
    launch_agents_dir.mkdir(parents=True, exist_ok=True)

    # Create logs directory
    logs_dir = Path.home() / "Library" / "Logs" / "CallTrackingCalendar"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Unload existing agent if loaded
    if is_loaded():
        unload()

    # Write the plist file
    plist_path = get_plist_path()
    plist_content = create_plist_content(sync_interval, run_at_load)

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_content, f)

    # Load the agent
    return load()


def uninstall() -> bool:
    """Uninstall the LaunchAgent.

    Returns:
        True if uninstallation succeeded.
    """
    # Unload if loaded
    if is_loaded():
        unload()

    # Remove the plist file
    plist_path = get_plist_path()
    if plist_path.exists():
        plist_path.unlink()
        return True

    return False


def load() -> bool:
    """Load the LaunchAgent.

    Returns:
        True if loading succeeded.
    """
    plist_path = get_plist_path()
    if not plist_path.exists():
        return False

    try:
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def unload() -> bool:
    """Unload the LaunchAgent.

    Returns:
        True if unloading succeeded.
    """
    plist_path = get_plist_path()
    if not plist_path.exists():
        return False

    try:
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def run_now() -> bool:
    """Trigger an immediate sync by starting the agent.

    Returns:
        True if the trigger succeeded.
    """
    if not is_loaded():
        if not load():
            return False

    try:
        result = subprocess.run(
            ["launchctl", "start", LAUNCH_AGENT_LABEL],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def get_status() -> dict:
    """Get the status of the LaunchAgent.

    Returns:
        Dictionary with status information.
    """
    return {
        "installed": is_installed(),
        "loaded": is_loaded(),
        "plist_path": str(get_plist_path()),
        "label": LAUNCH_AGENT_LABEL,
    }


def get_logs(lines: int = 50) -> str:
    """Get recent log output from the sync service.

    Args:
        lines: Number of lines to return.

    Returns:
        Recent log content.
    """
    log_path = (
        Path.home() / "Library" / "Logs" / "CallTrackingCalendar" / "sync.log"
    )

    if not log_path.exists():
        return "No logs found."

    try:
        with open(log_path) as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except OSError as e:
        return f"Error reading logs: {e}"

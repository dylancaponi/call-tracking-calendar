# Call Tracking Calendar - Development Notes

## Repository & Environment

- **This directory (`app/`) is the git repo root.** The parent (`call-tracking-calendar/`) is NOT a git repo.
- All git commands must run from `app/` with paths relative to it (e.g. `src/sync_service.py`, not `app/src/sync_service.py`).
- **Sandbox:** `git`, `pytest`, and `python` commands require `dangerouslyDisableSandbox: true` due to stdout restrictions.
- Chain git operations in a single command to avoid wasted calls: `git add <files> && git commit -m "msg" && git status`

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run the app
python -m src.main

# Run tests
pytest tests/ -v

# Run sync manually
python -m src.sync_service --verbose
```

## Key Files

- `src/call_database.py` - Reads macOS call history from SQLite database
- `src/google_calendar.py` - Google Calendar API wrapper with OAuth
- `src/sync_service.py` - Main sync logic, can be run standalone
- `src/ui/setup_wizard.py` - First-run setup UI (Tkinter)

## macOS Call Database

Location: `~/Library/Application Support/CallHistoryDB/CallHistory.storedata`

Key columns in `ZCALLRECORD`:
- `ZUNIQUE_ID` - Call identifier (NOT enforced unique — see below)
- `ZDATE` - Apple timestamp (add 978307200 for Unix timestamp)
- `ZDURATION` - Duration in seconds
- `ZANSWERED` - 1 if answered, 0 if missed
- `ZORIGINATED` - 1 if outgoing, 0 if incoming

**ZUNIQUE_ID is not SQL-unique.** The `Z` prefix is just Core Data's auto-naming
convention (all columns get `Z` + uppercase attribute name). Core Data manages
uniqueness at the object graph layer, not with SQL constraints. Since we read
the SQLite file directly (bypassing Core Data), duplicate rows can appear.
Deduplication is handled in two places:
- `call_database.py`: `GROUP BY ZUNIQUE_ID` in the SQL query (defense-in-depth)
- `sync_service.py`: `seen` set in the filtering loop (primary guard)

## OAuth Flow

The app uses desktop OAuth flow with loopback IP:
1. Opens browser to Google consent page
2. User grants permission
3. Google redirects to `http://127.0.0.1:PORT`
4. App exchanges code for tokens
5. Tokens stored in macOS Keychain

## LaunchAgent

Installed to: `~/Library/LaunchAgents/com.calltracking.calendar.plist`

Logs at: `~/Library/Logs/CallTrackingCalendar/sync.log`

Commands:
```bash
# Check status
launchctl list | grep calltracking

# Manual trigger
launchctl start com.calltracking.calendar

# Reload after changes
launchctl unload ~/Library/LaunchAgents/com.calltracking.calendar.plist
launchctl load ~/Library/LaunchAgents/com.calltracking.calendar.plist
```

## Testing Without Full Disk Access

Create a test database:
```python
import sqlite3
conn = sqlite3.connect('/tmp/test_calls.db')
conn.execute('''CREATE TABLE ZCALLRECORD (
    Z_PK INTEGER PRIMARY KEY,
    ZUNIQUE_ID TEXT,
    ZADDRESS TEXT,
    ZNAME TEXT,
    ZDATE REAL,
    ZDURATION REAL,
    ZANSWERED INTEGER,
    ZORIGINATED INTEGER
)''')
# Insert test data...
```

Then use: `CallDatabase(Path('/tmp/test_calls.db'))`

## Contacts Integration

Two backends for contact name lookup, checked in order:
1. **Contacts framework** (PyObjC) — works on macOS 13+ with PyObjC 12.x. No version gate needed.
2. **AddressBook SQLite DB** — legacy fallback at `~/Library/Application Support/AddressBook/AddressBook-v22.abcddb`. Often empty on modern macOS (contacts stored in CloudKit).

**Critical:** When using `predicateForContactsMatchingPhoneNumber_`, the fetch keys MUST include `CNContactPhoneNumbersKey` alongside name keys. Without it, the framework throws `CNPropertyNotFetchedException` which gets silently caught → all lookups return None.

## Sync State & Calendar ID Tracking

The sync DB stores the Google Calendar ID in settings. On each sync, if the stored calendar ID differs from the current one (user deleted the calendar), sync history is auto-cleared so calls re-sync. This avoids the confusing "skipped N already synced" state after calendar deletion.

## Common Issues

1. **"Unable to open database"** - Need Full Disk Access
2. **"No module named keyring"** - Activate venv first
3. **"credentials.json not found"** - Download from Google Cloud Console
4. **Tkinter issues on macOS** - May need `brew install python-tk`
5. **Contact names not showing** - Check Contacts permission for your terminal app in System Settings > Privacy & Security > Contacts

## Building

PyInstaller creates a standalone app bundle:
```bash
./scripts/build.sh
```

For distribution, need Apple Developer account for:
- Code signing (Gatekeeper)
- Notarization (prevents "unidentified developer" warning)

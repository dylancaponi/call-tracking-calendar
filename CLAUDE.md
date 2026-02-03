# Call Tracking Calendar - Development Notes

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
- `ZUNIQUE_ID` - Unique call identifier (use for deduplication)
- `ZDATE` - Apple timestamp (add 978307200 for Unix timestamp)
- `ZDURATION` - Duration in seconds
- `ZANSWERED` - 1 if answered, 0 if missed
- `ZORIGINATED` - 1 if outgoing, 0 if incoming

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

## Common Issues

1. **"Unable to open database"** - Need Full Disk Access
2. **"No module named keyring"** - Activate venv first
3. **"credentials.json not found"** - Download from Google Cloud Console
4. **Tkinter issues on macOS** - May need `brew install python-tk`

## Building

PyInstaller creates a standalone app bundle:
```bash
./scripts/build.sh
```

For distribution, need Apple Developer account for:
- Code signing (Gatekeeper)
- Notarization (prevents "unidentified developer" warning)

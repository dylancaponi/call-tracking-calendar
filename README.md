# Call Tracking Calendar

A macOS application that syncs your call history to Google Calendar. Each completed call appears as a calendar event, making it easy to track your communication history.

## Features

- Automatically syncs answered calls to a "Call Tracking" calendar
- Runs in the background every 5 minutes
- Shows contact names, call direction, and duration
- Secure: OAuth tokens stored in macOS Keychain
- Privacy-focused: Only call metadata (no recordings or content)

## Requirements

- macOS 10.15 (Catalina) or later
- Python 3.11+ (for development)
- Google account

## Installation

### For Users

1. Download the latest DMG from Releases
2. Open the DMG and drag the app to Applications
3. Launch the app and follow the setup wizard:
   - Grant Full Disk Access permission
   - Sign in with Google
   - Enable background sync

### For Developers

```bash
# Clone the repository
git clone https://github.com/yourusername/call-tracking-calendar.git
cd call-tracking-calendar

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python -m src.main
```

## Google Cloud Setup

Before the app can sync to Google Calendar, you need to set up OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download `credentials.json` and place it in `resources/`

## Usage

### Command Line Options

```bash
# Run the setup wizard
python -m src.main --setup

# Open preferences window
python -m src.main --preferences

# Run sync immediately
python -m src.main --sync

# Show sync status
python -m src.main --status
```

### Background Sync

The app installs a LaunchAgent that runs every 5 minutes to sync new calls. You can manage this in the Preferences window.

## Calendar Event Format

Each call creates an event like:

```
Title: Call with John Smith
Time: [Call start time] - [Call end time]
Description:
  Direction: Incoming
  Duration: 5 minutes 32 seconds
  Answered: Yes
  Number: +1-555-123-4567
```

## Development

### Project Structure

```
call-tracking-calendar/
├── src/
│   ├── main.py              # Entry point
│   ├── call_database.py     # Read macOS call history
│   ├── google_calendar.py   # Google Calendar API
│   ├── sync_database.py     # Local sync tracking
│   ├── sync_service.py      # Sync orchestration
│   ├── permissions.py       # Permission checking
│   ├── launchagent.py       # LaunchAgent management
│   └── ui/
│       ├── setup_wizard.py  # First-run setup
│       └── preferences.py   # Settings window
├── tests/                   # Unit tests
├── resources/               # LaunchAgent template, icons
└── scripts/                 # Build scripts
```

### Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

### Building for Distribution

```bash
# Build the app bundle
./scripts/build.sh

# Create DMG installer
./scripts/create_dmg.sh

# Notarize (requires Apple Developer account)
export APPLE_ID="your@email.com"
export TEAM_ID="YOURTEAMID"
export APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
./scripts/notarize.sh
```

## Permissions

The app requires **Full Disk Access** to read the call history database located at:
```
~/Library/Application Support/CallHistoryDB/CallHistory.storedata
```

This is a read-only operation. The app cannot modify or delete your call history.

## Privacy

- Only call metadata is accessed (time, duration, contact info)
- No call recordings or content is accessed
- Data is synced only to your own Google Calendar
- OAuth tokens are stored securely in macOS Keychain
- No data is sent to any third party

## License

MIT License - see LICENSE file for details.

## Troubleshooting

### "Full Disk Access required"

1. Open System Settings > Privacy & Security > Full Disk Access
2. Click the lock to make changes
3. Add the app (or Terminal if running from source)
4. Restart the app

### "Not authenticated with Google"

1. Open the app
2. Go to Settings tab
3. Click "Connect" to sign in with Google

### Calls not syncing

1. Check the Logs tab for errors
2. Verify background sync is enabled
3. Try "Sync Now" to trigger manual sync
4. Check if the "Call Tracking" calendar exists in Google Calendar

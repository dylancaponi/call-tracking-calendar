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
git clone https://github.com/dylancaponi/call-tracking-calendar.git
cd call-tracking-calendar

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python -m src.main
```

## Google Cloud Setup (For Developers/Self-Hosting)

To distribute this app or run it yourself, you need to create OAuth credentials:

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown (top left) → **New Project**
3. Name it "Call Tracking Calendar" → **Create**
4. Make sure your new project is selected

### Step 2: Enable the Google Calendar API

1. Go to **APIs & Services** → **Library**
2. Search for "Google Calendar API"
3. Click on it → **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** → **Create**
3. Fill in:
   - App name: `Call Tracking Calendar`
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. On Scopes page, click **Add or Remove Scopes**
   - Find and check `https://www.googleapis.com/auth/calendar`
   - Click **Update** → **Save and Continue**
6. On Test users page, add your email for testing → **Save and Continue**
7. Review and go back to dashboard

### Step 4: Create OAuth Credentials (Desktop App with PKCE)

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `Call Tracking Calendar Desktop`
5. Click **Create**
6. Click **Download JSON**
7. Rename the file to `credentials.json`
8. Place it in the `resources/` folder of this project

The downloaded file will look like this (no client_secret needed for Desktop apps):
```json
{
  "installed": {
    "client_id": "XXXX.apps.googleusercontent.com",
    "project_id": "your-project",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "redirect_uris": ["http://localhost"]
  }
}
```

### Step 5: For Production Distribution

Before distributing to users beyond testing:

1. Go back to **OAuth consent screen**
2. Click **Publish App** to move from Testing to Production
3. Submit for **Google Verification** (required if you have >100 users)
   - This prevents the "unverified app" warning
   - Requires privacy policy, terms of service, and review process

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

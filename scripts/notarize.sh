#!/bin/bash
# Notarize the Call Tracking Calendar application
# Requires: Apple Developer account, app-specific password

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
APP_NAME="CallTrackingCalendar"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$APP_NAME.dmg"

# Configuration - set these environment variables or modify here
APPLE_ID="${APPLE_ID:-}"
TEAM_ID="${TEAM_ID:-}"
APP_PASSWORD="${APP_PASSWORD:-}"  # App-specific password from appleid.apple.com
DEVELOPER_ID="${DEVELOPER_ID:-}"  # e.g., "Developer ID Application: Your Name (TEAMID)"

if [ -z "$APPLE_ID" ] || [ -z "$TEAM_ID" ] || [ -z "$APP_PASSWORD" ]; then
    echo "Error: Missing required environment variables"
    echo ""
    echo "Please set:"
    echo "  APPLE_ID - Your Apple ID email"
    echo "  TEAM_ID - Your Apple Developer Team ID"
    echo "  APP_PASSWORD - App-specific password from appleid.apple.com"
    echo "  DEVELOPER_ID - (optional) Your Developer ID certificate name"
    echo ""
    echo "Example:"
    echo "  export APPLE_ID='your@email.com'"
    echo "  export TEAM_ID='ABCD1234'"
    echo "  export APP_PASSWORD='xxxx-xxxx-xxxx-xxxx'"
    echo "  export DEVELOPER_ID='Developer ID Application: Your Name (ABCD1234)'"
    exit 1
fi

# Check if app bundle exists
if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: App bundle not found at $APP_BUNDLE"
    echo "Please run scripts/build.sh first"
    exit 1
fi

echo "=== Code Signing ==="

if [ -n "$DEVELOPER_ID" ]; then
    echo "Signing with: $DEVELOPER_ID"

    # Sign the sync executable
    codesign --deep --force --options runtime \
        --sign "$DEVELOPER_ID" \
        "$APP_BUNDLE/Contents/MacOS/sync"

    # Sign the main app
    codesign --deep --force --options runtime \
        --sign "$DEVELOPER_ID" \
        "$APP_BUNDLE"

    echo "Code signing complete"
else
    echo "Warning: DEVELOPER_ID not set, skipping code signing"
    echo "The app will not pass Gatekeeper without code signing"
fi

echo ""
echo "=== Creating DMG ==="

# Create the DMG
"$SCRIPT_DIR/create_dmg.sh"

if [ -n "$DEVELOPER_ID" ]; then
    # Sign the DMG
    codesign --force --sign "$DEVELOPER_ID" "$DMG_PATH"
fi

echo ""
echo "=== Notarizing ==="

# Submit for notarization
echo "Submitting to Apple for notarization..."
xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$APP_PASSWORD" \
    --wait

echo ""
echo "=== Stapling ==="

# Staple the notarization ticket
xcrun stapler staple "$DMG_PATH"

echo ""
echo "=== Complete ==="
echo "Notarized DMG: $DMG_PATH"
echo ""
echo "You can now distribute the DMG. Users can install by:"
echo "1. Opening the DMG"
echo "2. Dragging the app to Applications"
echo "3. Running the app (may need to right-click > Open on first launch)"

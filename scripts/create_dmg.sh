#!/bin/bash
# Create a DMG installer for Call Tracking Calendar

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
APP_NAME="CallTrackingCalendar"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
DMG_NAME="$APP_NAME.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
VOLUME_NAME="Call Tracking Calendar"

# Check if app bundle exists
if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: App bundle not found at $APP_BUNDLE"
    echo "Please run scripts/build.sh first"
    exit 1
fi

echo "Creating DMG installer..."

# Remove existing DMG if present
rm -f "$DMG_PATH"

# Create a temporary directory for the DMG contents
DMG_TEMP="$DIST_DIR/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy the app bundle
cp -R "$APP_BUNDLE" "$DMG_TEMP/"

# Create a symbolic link to /Applications
ln -s /Applications "$DMG_TEMP/Applications"

# Create the DMG
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# Clean up
rm -rf "$DMG_TEMP"

echo "DMG created: $DMG_PATH"
echo ""
echo "To distribute:"
echo "1. Code sign the app: codesign --deep --force --sign 'Developer ID Application: Your Name' $APP_BUNDLE"
echo "2. Notarize: xcrun notarytool submit $DMG_PATH --apple-id YOUR_EMAIL --team-id YOUR_TEAM_ID --password YOUR_APP_PASSWORD"
echo "3. Staple: xcrun stapler staple $DMG_PATH"

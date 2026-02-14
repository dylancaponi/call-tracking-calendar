#!/bin/bash
# Build the Call Tracking Calendar application bundle

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"
ICON_PATH="$PROJECT_DIR/resources/icon.icns"

echo "Building Call Tracking Calendar..."

# Clean previous builds
rm -rf "$BUILD_DIR" "$DIST_DIR"

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Install dependencies
pip install -r "$PROJECT_DIR/requirements.txt"

# Build icon flag if icon exists
ICON_FLAG=()
if [ -f "$ICON_PATH" ]; then
    ICON_FLAG=(--icon "$ICON_PATH")
    echo "Using app icon: $ICON_PATH"
else
    echo "Warning: No icon found at $ICON_PATH, using default PyInstaller icon"
fi

# Build the main app
echo "Building main application..."
pyinstaller \
    --name "CallTrackingCalendar" \
    --windowed \
    --onedir \
    --add-data "$PROJECT_DIR/resources:resources" \
    --hidden-import "keyring.backends.macOS" \
    --hidden-import "google.auth.transport.requests" \
    --hidden-import "google_auth_oauthlib.flow" \
    --hidden-import "googleapiclient.discovery" \
    --osx-bundle-identifier "com.calltracking.calendar" \
    --paths "$PROJECT_DIR" \
    "${ICON_FLAG[@]}" \
    "$PROJECT_DIR/launcher.py"

# Merge our custom Info.plist keys into the PyInstaller-generated one
APP_BUNDLE="$DIST_DIR/CallTrackingCalendar.app"
PLIST="$APP_BUNDLE/Contents/Info.plist"
CUSTOM_PLIST="$PROJECT_DIR/resources/Info.plist"

echo "Merging custom Info.plist keys..."
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'Call Tracking Calendar'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string '10.15'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string 'Copyright © 2024. All rights reserved.'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSContactsUsageDescription string 'Call Tracking Calendar needs access to your Contacts to show contact names in calendar events instead of phone numbers.'" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Call Tracking Calendar needs to open your web browser for Google authentication.'" "$PLIST" 2>/dev/null || true

# Build the sync service as a separate executable
echo "Building sync service..."
pyinstaller \
    --name "sync" \
    --onefile \
    --hidden-import "keyring.backends.macOS" \
    --hidden-import "google.auth.transport.requests" \
    --hidden-import "googleapiclient.discovery" \
    --paths "$PROJECT_DIR" \
    "$PROJECT_DIR/launcher_sync.py"

# Copy sync executable into the app bundle
cp "$DIST_DIR/sync" "$APP_BUNDLE/Contents/MacOS/"

echo "Build complete!"
echo "App bundle: $APP_BUNDLE"
echo ""
echo "Next steps:"
echo "1. Add your credentials.json to $APP_BUNDLE/Contents/Resources/resources/"
echo "2. Run scripts/create_dmg.sh to create the installer"
echo "3. Run scripts/notarize.sh to notarize for distribution (requires Apple Developer account)"

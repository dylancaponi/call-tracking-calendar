#!/bin/bash
# Build the Call Tracking Calendar application bundle

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"

echo "Building Call Tracking Calendar..."

# Clean previous builds
rm -rf "$BUILD_DIR" "$DIST_DIR"

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Install dependencies
pip install -r "$PROJECT_DIR/requirements.txt"

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
    "$PROJECT_DIR/src/main.py"

# Build the sync service as a separate executable
echo "Building sync service..."
pyinstaller \
    --name "sync" \
    --onefile \
    --hidden-import "keyring.backends.macOS" \
    --hidden-import "google.auth.transport.requests" \
    --hidden-import "googleapiclient.discovery" \
    "$PROJECT_DIR/src/sync_service.py"

# Copy sync executable into the app bundle
APP_BUNDLE="$DIST_DIR/CallTrackingCalendar.app"
cp "$DIST_DIR/sync" "$APP_BUNDLE/Contents/MacOS/"

# Create Info.plist additions
cat >> "$APP_BUNDLE/Contents/Info.plist.additions" << 'EOF'
    <key>LSUIElement</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
EOF

echo "Build complete!"
echo "App bundle: $APP_BUNDLE"
echo ""
echo "Next steps:"
echo "1. Add your credentials.json to $APP_BUNDLE/Contents/Resources/resources/"
echo "2. Run scripts/create_dmg.sh to create the installer"
echo "3. Run scripts/notarize.sh to notarize for distribution (requires Apple Developer account)"

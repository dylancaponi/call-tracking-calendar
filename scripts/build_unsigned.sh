#!/bin/bash
# Build an unsigned DMG for testing (no Apple Developer account needed)
#
# The resulting DMG can be installed by:
# 1. Open the DMG, drag CallTrackingCalendar to Applications
# 2. Right-click the app > Open (first launch only, to bypass Gatekeeper)
# 3. Or: System Settings > Privacy & Security > "Open Anyway"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"

echo "=== Building unsigned DMG for testing ==="
echo ""

# Step 1: Build the app
"$SCRIPT_DIR/build.sh"

# Step 2: Ad-hoc sign so macOS Keychain works (no Developer ID needed)
APP_BUNDLE="$DIST_DIR/CallTrackingCalendar.app"
echo "Ad-hoc signing for Keychain access..."
codesign --force --deep --sign - "$APP_BUNDLE"

# Step 3: Add install instructions to the DMG
cat > "$DIST_DIR/INSTALL.txt" << 'EOF'
Call Tracking Calendar - Installation

1. Drag "CallTrackingCalendar" to the Applications folder.

2. On first launch, macOS will block the app because it's unsigned.
   To open it:
   - Right-click (or Control-click) the app and select "Open"
   - Click "Open" in the dialog that appears
   - You only need to do this once

   Alternatively:
   - Go to System Settings > Privacy & Security
   - Scroll down and click "Open Anyway" next to the blocked app

3. The app requires Full Disk Access to read your call history.
   Go to: System Settings > Privacy & Security > Full Disk Access
   Toggle on "CallTrackingCalendar"

4. Follow the setup wizard to connect your Google Calendar.
EOF

# Step 4: Create the DMG
"$SCRIPT_DIR/create_dmg.sh"

echo ""
echo "=== Done ==="
echo "Unsigned DMG: $DIST_DIR/CallTrackingCalendar.dmg"
echo ""
echo "To install:"
echo "  1. Open the DMG"
echo "  2. Drag CallTrackingCalendar to Applications"
echo "  3. Right-click the app > Open (first launch only)"

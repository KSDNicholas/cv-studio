#!/bin/bash
# Build "CV Studio.app" (icon + launcher) and copy it to the Desktop. Safe to rerun after editing icon.svg.
# Usage: launcher/build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
APP="$HERE/build/CV Studio.app"

"$REPO/.venv/bin/python" "$HERE/render_icon.py"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
iconutil -c icns "$HERE/build/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
sed "s|__REPO__|$REPO|" "$HERE/cv-studio.sh" > "$APP/Contents/MacOS/cv-studio"
chmod +x "$APP/Contents/MacOS/cv-studio"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>CV Studio</string>
  <key>CFBundleDisplayName</key><string>CV Studio</string>
  <key>CFBundleIdentifier</key><string>local.cvstudio.app</string>
  <key>CFBundleExecutable</key><string>cv-studio</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>LSArchitecturePriority</key><array><string>arm64</string><string>x86_64</string></array>
</dict>
</plist>
PLIST
xattr -cr "$APP"
rm -rf "$HOME/Desktop/CV Studio.app"
cp -R "$APP" "$HOME/Desktop/CV Studio.app"
touch "$HOME/Desktop/CV Studio.app"
echo "Built $APP and copied it to ~/Desktop/CV Studio.app"

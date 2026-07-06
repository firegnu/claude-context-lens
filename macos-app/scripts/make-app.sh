#!/usr/bin/env bash
# Package the SwiftPM executable into a double-clickable ContextLens.app.
# Usage: scripts/make-app.sh [DEST_DIR]   (default: ~/Applications)
set -euo pipefail

PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)"        # macos-app/
APP_NAME="ContextLens"
DEST="${1:-$HOME/Applications}"
APP="$DEST/$APP_NAME.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Building release binary..."
swift build -c release --package-path "$PKG_DIR"
BIN="$(swift build -c release --package-path "$PKG_DIR" --show-bin-path)/ContextLensApp"

echo "==> Rendering icon..."
swift "$PKG_DIR/scripts/render-icon.swift" "$TMP/icon-1024.png" >/dev/null
ICONSET="$TMP/AppIcon.iconset"; mkdir -p "$ICONSET"
gen() { sips -z "$2" "$2" "$TMP/icon-1024.png" --out "$ICONSET/$1" >/dev/null; }
gen icon_16x16.png 16;    gen icon_16x16@2x.png 32
gen icon_32x32.png 32;    gen icon_32x32@2x.png 64
gen icon_128x128.png 128; gen icon_128x128@2x.png 256
gen icon_256x256.png 256; gen icon_256x256@2x.png 512
gen icon_512x512.png 512; gen icon_512x512@2x.png 1024

echo "==> Assembling $APP..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$APP_NAME"
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ContextLens</string>
  <key>CFBundleDisplayName</key><string>ContextLens</string>
  <key>CFBundleExecutable</key><string>ContextLens</string>
  <key>CFBundleIdentifier</key><string>com.firegnu.contextlens</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

echo "==> Done: $APP"
echo "    Open it: open \"$APP\"   (or double-click / Spotlight \"ContextLens\")"

#!/bin/bash
# Builds PlaylistTransferer.app — bundles the SwiftUI frontend and PyInstaller backend.
set -euo pipefail

BUNDLE="PlaylistTransferer.app"

echo "→ Building Python backend (PyInstaller)…"
.venv/bin/pyinstaller \
    --onefile \
    --name playlist-backend \
    --distpath dist-backend \
    --workpath build-pyinstaller \
    --specpath build-pyinstaller \
    backend.py

echo "→ Building Swift app (release)…"
swift build -c release --package-path swift-app

echo "→ Assembling $BUNDLE…"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS"
mkdir -p "$BUNDLE/Contents/Resources"

cp swift-app/.build/release/PlaylistTransferer "$BUNDLE/Contents/MacOS/"
cp dist-backend/playlist-backend               "$BUNDLE/Contents/Resources/"
cp swift-app/Info.plist                        "$BUNDLE/Contents/"

echo ""
echo "✓  $BUNDLE is ready."
echo ""
echo "   First launch: right-click → Open (Gatekeeper will block double-click"
echo "   on unsigned apps — this is expected for apps built outside the App Store)."
echo ""
echo "   Or bypass once with:"
echo "     xattr -cr $BUNDLE"

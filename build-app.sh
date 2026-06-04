#!/bin/bash
# Builds PlaylistTransferer.app -- bundles the SwiftUI frontend and PyInstaller backend.
set -euo pipefail

BUNDLE="dist/PlaylistTransferer.app"

echo "==> Building Python backend (PyInstaller)..."
backend/.venv/bin/pyinstaller \
    --onefile \
    --name playlist-backend \
    --distpath dist-backend \
    --workpath build-pyinstaller \
    --specpath build-pyinstaller \
    backend/backend.py

echo "==> Building Swift app (release)..."
swift build -c release --package-path swift-app

echo "==> Assembling ${BUNDLE}..."
mkdir -p dist
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS"
mkdir -p "$BUNDLE/Contents/Resources"

cp swift-app/.build/release/PlaylistTransferer "$BUNDLE/Contents/MacOS/"
cp dist-backend/playlist-backend               "$BUNDLE/Contents/Resources/"
cp swift-app/Info.plist                        "$BUNDLE/Contents/"

echo ""
echo "Done: ${BUNDLE}"
echo ""
echo "First launch: right-click -> Open (Gatekeeper blocks unsigned apps)."
echo "Or clear quarantine once with:  xattr -cr ${BUNDLE}"

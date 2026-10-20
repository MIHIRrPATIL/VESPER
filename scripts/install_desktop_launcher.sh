#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_SRC="${ROOT_DIR}/desktop/src-tauri/target/release/tauri-app"
BIN_DST="${HOME}/.local/bin/vesper-desktop"
ICON_SRC="${ROOT_DIR}/desktop/src-tauri/icons/128x128.png"
ICON_DST="${HOME}/.local/share/icons/hicolor/128x128/apps/vesper-desktop.png"
DESKTOP_DST="${HOME}/.local/share/applications/vesper-desktop.desktop"

echo "[VESPER] Deploying Tauri Desktop App locally..."

if [[ ! -f "${BIN_SRC}" ]]; then
    echo "[VESPER] Error: release binary not found at ${BIN_SRC}"
    echo "[VESPER] Run 'cd desktop && npm run tauri build -- -b deb' first."
    exit 1
fi

mkdir -p "${HOME}/.local/bin"
mkdir -p "${HOME}/.local/share/icons/hicolor/128x128/apps"
mkdir -p "${HOME}/.local/share/applications"

cp "${BIN_SRC}" "${BIN_DST}"
chmod +x "${BIN_DST}"
echo "[VESPER] Installed binary -> ${BIN_DST}"

cp "${ICON_SRC}" "${ICON_DST}"
echo "[VESPER] Installed icon -> ${ICON_DST}"

cat << 'EOF' > "${DESKTOP_DST}"
[Desktop Entry]
Name=VESPER Desk Companion HUD
Comment=Autonomous Multi-Agent AI Butler Desk Companion HUD
Exec=/home/mihir/.local/bin/vesper-desktop
Icon=vesper-desktop
Terminal=false
Type=Application
Categories=Utility;Office;ArtificialIntelligence;
StartupWMClass=tauri-app
Keywords=vesper;ai;butler;hud;desk;
EOF

chmod +x "${DESKTOP_DST}"
echo "[VESPER] Installed desktop launcher -> ${DESKTOP_DST}"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${HOME}/.local/share/applications" || true
fi

echo "[VESPER] Desktop app successfully deployed!"
echo "[VESPER] You can launch it with: vesper-desktop"

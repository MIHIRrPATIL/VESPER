#!/usr/bin/env bash
# VESPER Systemd User Services Installer
# Configures background services to run headlessly under systemd --user on Arch Linux.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python3"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if [ ! -f "${VENV_PYTHON}" ]; then
    echo "[ERROR] Python virtual environment not found at: ${VENV_PYTHON}"
    exit 1
fi

mkdir -p "${SYSTEMD_USER_DIR}"

echo "[INFO] Installing VESPER systemd --user services..."
echo "[INFO] Repository Root: ${REPO_DIR}"
echo "[INFO] Python Executable: ${VENV_PYTHON}"
echo "[INFO] Destination: ${SYSTEMD_USER_DIR}"

# 1. Gateway Service
cat <<EOF > "${SYSTEMD_USER_DIR}/vesper-gateway.service"
[Unit]
Description=VESPER Multiplexed Gateway Service
After=network.target
PartOf=vesper.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m uvicorn backend.gateway.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# 2. Agent Service
cat <<EOF > "${SYSTEMD_USER_DIR}/vesper-agent.service"
[Unit]
Description=VESPER Swarm Agent Service
After=network.target vesper-gateway.service
Wants=vesper-gateway.service
PartOf=vesper.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m uvicorn backend.agent.app:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# 3. Voice Service
cat <<EOF > "${SYSTEMD_USER_DIR}/vesper-voice.service"
[Unit]
Description=VESPER Voice Pipeline Service (Piper TTS / Whisper / Wake Word)
After=network.target vesper-gateway.service
Wants=vesper-gateway.service
PartOf=vesper.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m uvicorn backend.voice.app:app --host 0.0.0.0 --port 8002
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# 4. Workstation Daemon
cat <<EOF > "${SYSTEMD_USER_DIR}/vesper-workstation.service"
[Unit]
Description=VESPER Local Workstation Daemon (Wayland/Hyprland DPMS, OCR, Audio Sinks)
After=graphical-session.target vesper-gateway.service
Wants=vesper-gateway.service
PartOf=vesper.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} backend/workstation/daemon.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
PassEnvironment=DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR PULSE_SERVER HYPRLAND_INSTANCE_SIGNATURE
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# 5. Composite Target
cat <<EOF > "${SYSTEMD_USER_DIR}/vesper.target"
[Unit]
Description=VESPER Intelligent OS Full Stack Target
Wants=vesper-gateway.service vesper-agent.service vesper-voice.service vesper-workstation.service

[Install]
WantedBy=default.target
EOF

# Reload user systemd daemon
systemctl --user daemon-reload

echo "[SUCCESS] VESPER user service units installed and daemon reloaded."
echo ""
echo "Manage services using standard systemctl commands:"
echo "  Start all:        systemctl --user start vesper.target"
echo "  Stop all:         systemctl --user stop vesper.target"
echo "  Enable on boot:   systemctl --user enable vesper.target"
echo "  Check status:     systemctl --user status vesper-gateway vesper-agent vesper-voice vesper-workstation"
echo "  View logs:        journalctl --user -u vesper-gateway -f"
echo "                    journalctl --user -u vesper-workstation -f"

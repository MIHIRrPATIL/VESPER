#!/usr/bin/env python3
"""Google Calendar OAuth 2.0 Authorization Script for VESPER.

Delegates to unified Google Workspace authorization script:
    .venv/bin/python3 scripts/auth_google_calendar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Delegate to unified Google authorization script (Gmail + Calendar)
from scripts.auth_google import main

if __name__ == "__main__":
    main()

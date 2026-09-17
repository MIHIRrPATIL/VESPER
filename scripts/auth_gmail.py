#!/usr/bin/env python3
"""Google Gmail OAuth 2.0 Authorization Script for VESPER.

Run this script once to authorize VESPER to access your Gmail inbox:
    .venv/bin/python3 scripts/auth_gmail.py
"""

import sys
from pathlib import Path

# Delegate to unified Google authorization script (Gmail + Calendar)
from scripts.auth_google import main

if __name__ == "__main__":
    main()

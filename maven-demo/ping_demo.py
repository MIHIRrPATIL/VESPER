"""MAVEN diff-scan demo file: intentionally vulnerable. Do not merge.

Added only to show a *new* finding in the MAVEN PR comment and SARIF annotations.
"""

import os


def ping(host):
    os.system("ping -c 1 " + host)  # command injection (CWE-78), on purpose

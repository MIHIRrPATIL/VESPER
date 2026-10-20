#!/usr/bin/env python3
"""VESPER Standalone Notification Backlog Processor.

Triages notification backlogs stored in JSON files or fetched from the
local VESPER cluster, evaluating temporal relevance, bank transactions,
and communication tasks in batches.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agent.tools.notification_batch_tool import triage_notification_backlog_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("process_notification_backlog")


async def main() -> None:
    parser = argparse.ArgumentParser(description="VESPER Notification Backlog Batch Triage")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        help="Path to JSON file containing array of notification payloads",
    )
    parser.add_argument(
        "--device-name",
        type=str,
        default="Mobile Companion",
        help="Name of the reporting mobile device",
    )
    args = parser.parse_args()

    notifications = []
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"Input file not found: {args.input}")
            sys.exit(1)
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                notifications = data
            elif isinstance(data, dict) and "notifications" in data:
                notifications = data["notifications"]
            else:
                logger.error("Invalid JSON structure: expected list or {notifications: [...]}")
                sys.exit(1)
    else:
        logger.info("No input file provided. Using sample mobile reconnect backlog for demonstration.")
        notifications = [
            {
                "package_name": "com.saraswatbank.mobile",
                "app_name": "Saraswat Bank",
                "title": "VK-SRCBBK",
                "text": "Your A/C ending 4091 has been debited by Rs. 2,450.00 on 20-Oct-26 at SWIGGY BANGALORE. Avl Bal: Rs 48,210.00",
                "timestamp": 1776681000.0,
            },
            {
                "package_name": "com.google.android.apps.messaging",
                "app_name": "Messages",
                "title": "AD-FLPKRT",
                "text": "Mega sale starts tonight! Use code SAVE50 to get 50% discount on electronics.",
                "timestamp": 1776670000.0,
            },
            {
                "package_name": "com.google.android.apps.messaging",
                "app_name": "Messages",
                "title": "VK-HDFCBK",
                "text": "583920 is your OTP for HDFC NetBanking login. Valid for 10 minutes. Do not share.",
                "timestamp": 1776600000.0,  # 80,000s ago -> expired!
            },
            {
                "package_name": "com.whatsapp",
                "app_name": "WhatsApp",
                "title": "Hitanshu Gala",
                "text": "Hey Mihir, please send the latest multiagent architecture diagram when you get back to your desk.",
                "timestamp": 1776680000.0,
            },
        ]

    logger.info(f"Loaded {len(notifications)} notification(s) for batch triage.")
    result = await triage_notification_backlog_batch(
        notifications=notifications,
        device_name=args.device_name,
    )

    print("\n--- BATCH TRIAGE REPORT ---")
    print(f"Total Received:     {result['total_received']}")
    print(f"Retained (Actionable): {result['retained_count']}")
    print(f"Filtered / Stale:   {result['stale_or_ignored_count']}")
    print(f"Financial Staged:   {result['financial_count']}")
    print(f"Tasks Staged:       {result['tasks_count']}")
    print("\nCatch-Up Briefing:")
    print(f"  {result['catch_up_briefing']}")
    print("\nItem Details:")
    for it in result.get("items", []):
        status = "KEEP" if it["retained"] else "DISCARD"
        print(f"  [{status}] ID: {it['id']} | Category: {it['category']} | Reason: {it['reason']}")
    print("---------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())

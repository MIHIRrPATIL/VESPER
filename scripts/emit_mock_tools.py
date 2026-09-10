#!/usr/bin/env python3
"""VESPER Mock Tool Call Emitter CLI Script.

Allows emitting mock specialist tool executions and HUD cards for inspection.
Can run standalone or connect to the running VESPER Gateway WebSocket.

Usage:
    # List all available mock tools and categories
    python scripts/emit_mock_tools.py --list

    # Emit a specific tool
    python scripts/emit_mock_tools.py --tool email.list_emails
    python scripts/emit_mock_tools.py --tool weather.get_current_weather --to-gateway

    # Emit an entire category
    python scripts/emit_mock_tools.py --group finance
    python scripts/emit_mock_tools.py --group productivity --to-gateway

    # Emit all tools in swarm sequence
    python scripts/emit_mock_tools.py --all --to-gateway --delay 0.8
"""

import argparse
import asyncio
import json
import random
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import websockets
except ImportError:
    websockets = None


# Registry of mock tools and realistic payloads matching HudDrawer contracts
MOCK_TOOLS: Dict[str, Dict[str, Any]] = {
    "email.list_emails": {
        "specialist": "Email & Correspondence Specialist",
        "category": "productivity",
        "description": "Fetches unread inbox messages, parses senders, snippets, and priorities",
        "hud_type": "email",
        "card_title": "UNREAD INBOX & CORRESPONDENCE",
        "args": {"max_results": 5, "query": "is:unread"},
        "result": {"status": "success", "total_unread": 2},
        "hud_data": {
            "title": "Unread Executive Correspondence",
            "emails": [
                {
                    "id": "em_1",
                    "sender": "Satya Nadella <satya@microsoft.com>",
                    "subject": "VESPER Edge AI Deployment Review",
                    "snippet": "Mihir, following up on our discussion regarding edge inference benchmarks and Jetson Orin integration...",
                    "date": "10m ago",
                    "unread": True,
                },
                {
                    "id": "em_2",
                    "sender": "GitHub Notifications <notifications@github.com>",
                    "subject": "[VESPER] PR #42 merged: TensorRT Jetson Zero-Copy DMA",
                    "snippet": "Your pull request was successfully verified and merged into main branch.",
                    "date": "28m ago",
                    "unread": True,
                },
            ],
        },
    },
    "task.list_tasks": {
        "specialist": "Task & Google Calendar Manager",
        "category": "productivity",
        "description": "Queries active deliverables, overdue priorities, and completion states",
        "hud_type": "task",
        "card_title": "ACTIVE TASKS & EXECUTIVE AGENDA",
        "args": {"status": "pending", "sort": "deadline"},
        "result": {"count": 3, "source": "Supabase + Google Tasks"},
        "hud_data": {
            "title": "Today's High-Priority Deliverables",
            "tasks": [
                {"id": "t1", "title": "Finalize Jetson MIPI CSI zero-copy pipeline", "done": False, "priority": "urgent", "deadline": "17:00"},
                {"id": "t2", "title": "Review Google Calendar sync cron logs", "done": True, "priority": "high", "deadline": "12:00"},
                {"id": "t3", "title": "Audit Supabase ledger balance triggers", "done": False, "priority": "normal", "deadline": "Tomorrow"},
            ],
        },
    },
    "calendar.list_events": {
        "specialist": "Task & Google Calendar Manager",
        "category": "productivity",
        "description": "Fetches today's synchronized appointments and Google Meet schedules",
        "hud_type": "calendar",
        "card_title": "GOOGLE CALENDAR & APPOINTMENTS",
        "args": {"time_min": "now", "time_max": "end_of_day"},
        "result": {"event_count": 2, "sync_status": "ok"},
        "hud_data": {
            "title": "Google Calendar Agenda",
            "date": "Thursday, September 10",
            "events": [
                {"id": "ev_1", "title": "VESPER Cognitive Mesh Architecture Review", "time": "15:00 - 16:00", "location": "Google Meet", "attendees": 4},
                {"id": "ev_2", "title": "Edge Inference Latency Benchmark", "time": "17:30 - 18:15", "location": "Lab Workstation", "attendees": 2},
            ],
        },
    },
    "finance.get_balance": {
        "specialist": "Financial Ledger & Intelligence",
        "category": "finance",
        "description": "Retrieves current account balances and recent transaction ledger entries",
        "hud_type": "transaction",
        "card_title": "FINANCIAL LEDGER & TRANSACTIONS",
        "args": {"account_id": "primary_hdfc", "include_recent": True},
        "result": {"current_balance": 428450.00, "currency": "INR"},
        "hud_data": {
            "account": "HDFC Premium Imperia **8492",
            "total_balance": "INR 4,28,450.00",
            "currency": "INR",
            "transactions": [
                {
                    "id": "tx_01",
                    "description": "NVIDIA Developer Store (Jetson Orin)",
                    "amount": "-INR 48,900.00",
                    "type": "debit",
                    "date": "Today, 14:15",
                    "category": "Hardware R&D",
                },
                {
                    "id": "tx_02",
                    "description": "Stripe Payout (SaaS Licensing)",
                    "amount": "+INR 1,85,000.00",
                    "type": "credit",
                    "date": "Yesterday, 09:30",
                    "category": "Revenue",
                },
            ],
        },
    },
    "weather.get_current_weather": {
        "specialist": "Atmospheric & Weather Intelligence",
        "category": "intel",
        "description": "Queries live meteorological radar, humidity, wind, and rain projections",
        "hud_type": "weather",
        "card_title": "ATMOSPHERIC INTELLIGENCE & RADAR",
        "args": {"latitude": 19.076, "longitude": 72.877, "hourly": True},
        "result": {"temp": 28.4, "condition": "Partly Cloudy", "rain_prob": 15},
        "hud_data": {
            "city": "Mumbai",
            "temp": "28 deg C",
            "condition": "Partly Cloudy",
            "humidity": "68%",
            "wind": "14 km/h SW",
            "uv_index": "3 Moderate",
            "forecast": [
                {"day": "Today", "temp": "31 / 26", "condition": "Partly Cloudy"},
                {"day": "Tomorrow", "temp": "30 / 25", "condition": "Scattered Rain"},
                {"day": "Saturday", "temp": "29 / 24", "condition": "Thunderstorm"},
            ],
        },
    },
    "research.web_search": {
        "specialist": "Deep Web & Research Specialist",
        "category": "intel",
        "description": "Executes multi-source DuckDuckGo queries and synthesizes verified citations",
        "hud_type": "research",
        "card_title": "DEEP RESEARCH & SYNTHESIS",
        "args": {"query": "NVIDIA Jetson Orin TensorRT zero copy DMA latency", "num_results": 3},
        "result": {"sources_found": 2, "synthesis_token_count": 142},
        "hud_data": {
            "query": "NVIDIA Jetson Orin TensorRT zero copy DMA latency",
            "summary": "Hardware zero-copy direct memory access (NVMM) bypassing host CPU memory achieves sub-5ms inference times on Orin Nano/NX for lightweight vision models. Network transmission over gigabit LAN adds < 1ms overhead.",
            "sources": [
                {"title": "NVIDIA Jetson Linux Developer Guide: Direct DMA ISP", "url": "https://docs.nvidia.com/jetson"},
                {"title": "TensorRT FP16 Execution Benchmarks", "url": "https://developer.nvidia.com/tensorrt"},
            ],
        },
    },
    "media.get_current_playback": {
        "specialist": "Spotify & Media Audio Engine",
        "category": "media",
        "description": "Inspects active Spotify track, artist, album art, and progress timestamp",
        "hud_type": "spotify",
        "card_title": "SPOTIFY AUDIO ENGINE & PLAYBACK",
        "args": {"include_progress": True},
        "result": {"is_playing": True, "service": "Spotify Web API"},
        "hud_data": {
            "track": "Starboy",
            "track_title": "Starboy",
            "artist": "The Weeknd, Daft Punk",
            "album": "Starboy",
            "is_playing": True,
            "duration_ms": 230453,
            "progress_ms": 114200,
            "cover_url": "https://i.scdn.co/image/ab67616d0000b2734718e2b124f79258be7bc452",
            "url": "https://open.spotify.com/track/7MXVkk9YM5IZxh0WSlVIk0",
        },
    },
    "youtube.search_videos": {
        "specialist": "Media & Entertainment Specialist",
        "category": "media",
        "description": "Searches YouTube videos, transcribes key chapters, and caches playback links",
        "hud_type": "youtube",
        "card_title": "YOUTUBE MEDIA RUNTIME",
        "args": {"query": "Lex Fridman Personal AI Companions", "max_results": 1},
        "result": {"video_id": "dQw4w9WgXcQ", "duration": "2:45:10"},
        "hud_data": {
            "title": "Lex Fridman Podcast: Building Autonomous Personal AI Companions",
            "channel": "Lex Fridman",
            "video_id": "dQw4w9WgXcQ",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "thumbnail": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "duration": "2:45:10",
            "snippet": "A deep dive into local multimodal intelligence, edge hardware, and tactile personal assistants.",
        },
    },
    "recipe.get_recipe": {
        "specialist": "Culinary & Nutrition Specialist",
        "category": "media",
        "description": "Parses culinary recipes into ingredients, prep times, and step-by-step timers",
        "hud_type": "recipe",
        "card_title": "CULINARY & NUTRITION SPECIALIST",
        "args": {"dish": "Espresso Tonic", "servings": 1},
        "result": {"prep_time_min": 5, "difficulty": "easy"},
        "hud_data": {
            "title": "Classic Pour-Over Espresso Tonic",
            "prep_time": "5 mins",
            "servings": 1,
            "ingredients": [
                "Double shot espresso (chilled)",
                "200ml Premium Indian Tonic Water",
                "Fresh orange peel or slice",
                "Cubed ice",
            ],
            "steps": [
                "Fill a chilled highball glass to the brim with clear ice cubes.",
                "Pour 200ml of tonic water down the side of the glass.",
                "Gently float the double espresso shot over the back of a bar spoon.",
                "Express orange peel oils over the surface and drop in the slice.",
            ],
        },
    },
    "system.get_system_stats": {
        "specialist": "System Operations & Hardware Manager",
        "category": "system_code",
        "description": "Reads host CPU, RAM, GPU temperature, uptime, and DPMS screen power states",
        "hud_type": "system_status",
        "card_title": "SYSTEM TELEMETRY & HARDWARE SENTRY",
        "args": {"probe_sensors": True, "include_gpu": True},
        "result": {"cpu_cores": 16, "ram_total_gb": 32.0, "dpms": "on"},
        "hud_data": {
            "hostname": "mihir-arch",
            "os": "Arch Linux (Kernel 6.16.8-zen)",
            "uptime": "4 days, 18 hours",
            "cpu_pct": 14.2,
            "cpu_temp": "46 deg C",
            "ram_used_gb": 6.8,
            "ram_total_gb": 32.0,
            "gpu_model": "NVIDIA RTX 4070 Laptop",
            "gpu_util_pct": 8.0,
            "display_power": "DPMS On (Active)",
        },
    },
    "github.list_pull_requests": {
        "specialist": "GitHub & DevOps Specialist",
        "category": "system_code",
        "description": "Queries repository pull requests, commit status, and diff statistics",
        "hud_type": "github",
        "card_title": "GITHUB REPOSITORY & DEVOPS",
        "args": {"repo": "MIHIRrPATIL/VESPER", "state": "all"},
        "result": {"open_prs": 1, "closed_prs": 1},
        "hud_data": {
            "repo": "MIHIRrPATIL/VESPER",
            "branch": "main",
            "prs": [
                {
                    "number": 42,
                    "title": "feat: touchless air tap drawer toggle & monastic zen mode",
                    "author": "mihir",
                    "status": "open",
                    "additions": 380,
                    "deletions": 12,
                },
                {
                    "number": 41,
                    "title": "fix: Supabase financial ledger sync webhook retry",
                    "author": "mihir",
                    "status": "merged",
                    "additions": 45,
                    "deletions": 8,
                },
            ],
            "issues": [
                {
                    "number": 19,
                    "title": "Support MIPI CSI-2 hardware ISP pipeline on Jetson Orin",
                    "author": "mihir",
                    "status": "open",
                },
            ],
        },
    },
    "system.control_display_power": {
        "specialist": "System Operations & Hardware Manager",
        "category": "system_code",
        "description": "Direct DPMS hardware control for waking or locking desktop monitors",
        "hud_type": "tool_call",
        "card_title": "TOOL EXECUTION DECK",
        "args": {"action": "wake", "target_display": "DP-3", "method": "dpms_force"},
        "result": {"status": "success", "dpms_state": "active", "latency_ms": 18},
        "hud_data": {
            "title": "system.control_display_power",
            "tool_name": "system.control_display_power",
            "specialist": "System Operations & Hardware Manager",
            "arguments": {"action": "wake", "target_display": "DP-3", "method": "dpms_force"},
            "result": {"status": "success", "dpms_state": "active", "latency_ms": 18},
        },
    },
}

CATEGORIES = ["productivity", "finance", "intel", "media", "system_code"]


def print_tool_envelope(tool_name: str, tool_def: Dict[str, Any], latency_ms: int) -> None:
    """Prints a structured tool execution summary to stdout."""
    print("=" * 72)
    print(f"[TOOL EXECUTION] {tool_name}")
    print(f"  Specialist:  {tool_def['specialist']}")
    print(f"  Category:    {tool_def['category']}")
    print(f"  Latency:     {latency_ms}ms")
    print(f"  Description: {tool_def['description']}")
    print("-" * 72)
    print("Dispatched Arguments:")
    print(json.dumps(tool_def["args"], indent=2))
    print("-" * 72)
    print("Returned Result:")
    print(json.dumps(tool_def["result"], indent=2))
    print("-" * 72)
    print("HUD Card Payload:")
    print(json.dumps(tool_def["hud_data"], indent=2))
    print("=" * 72)
    print()


def build_websocket_envelope(tool_name: str, tool_def: Dict[str, Any]) -> Dict[str, Any]:
    """Constructs a standard VESPER gateway envelope for the tool emission."""
    hud_card = {
        "id": str(uuid.uuid4()),
        "type": tool_def["hud_type"],
        "title": tool_def["card_title"],
        "data": tool_def["hud_data"],
        "timestamp": int(time.time() * 1000),
        "dismissed": False,
    }
    return {
        "channel": "CHAT",
        "type": "AGENT_RESPONSE",
        "uuid": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "payload": {
            "text": f"[TOOL_CALL] {tool_name} executed successfully.",
            "intent": tool_def["hud_type"].upper(),
            "hud_cards": [hud_card],
            "agent_state": "IDLE",
        },
    }


async def emit_over_websocket(ws_url: str, envelopes: List[Dict[str, Any]], delay: float = 0.5) -> None:
    """Connects to the Gateway WebSocket and sends envelopes sequentially."""
    if websockets is None:
        print("[ERROR] 'websockets' library is required to transmit over WebSocket. Install via: pip install websockets")
        return

    try:
        async with websockets.connect(ws_url) as ws:
            # Send initial HELLO
            hello = {
                "channel": "SYSTEM",
                "type": "HELLO",
                "uuid": str(uuid.uuid4()),
                "timestamp": int(time.time() * 1000),
                "payload": {"client_id": "mock-tool-emitter-cli", "device_type": "cli"},
            }
            await ws.send(json.dumps(hello))

            for env in envelopes:
                await ws.send(json.dumps(env))
                tool_text = env["payload"]["text"]
                print(f"[TRANSMITTED] Dispatched to Gateway ({ws_url}): {tool_text}")
                if len(envelopes) > 1:
                    await asyncio.sleep(delay)
    except Exception as e:
        print(f"[ERROR] Could not connect to WebSocket at {ws_url}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VESPER Mock Tool Call Emitter & HUD Inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="List all available mock tools and categories")
    parser.add_argument("--tool", type=str, help="Name of the specific tool to emit (e.g. email.list_emails)")
    parser.add_argument("--group", type=str, choices=CATEGORIES, help="Emit all tools in a specific category")
    parser.add_argument("--all", action="store_true", help="Emit all registered mock tools in sequence")
    parser.add_argument("--to-gateway", action="store_true", help="Transmit envelopes to running Gateway WebSocket (ws://localhost:8000/ws)")
    parser.add_argument("--ws-url", type=str, default="ws://localhost:8000/ws", help="Gateway WebSocket URL")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between sequential emissions")

    args = parser.parse_args()

    if args.list:
        print("VESPER Available Mock Tools Catalogue:")
        print("=" * 60)
        for cat in CATEGORIES:
            print(f"\n[Category: {cat.upper()}]")
            for t_id, t_def in MOCK_TOOLS.items():
                if t_def["category"] == cat:
                    print(f"  - {t_id:30} ({t_def['specialist']})")
                    print(f"    {t_def['description']}")
        print("=" * 60)
        return

    # Determine targets
    target_tools: List[str] = []
    if args.tool:
        if args.tool not in MOCK_TOOLS:
            print(f"[ERROR] Unknown tool '{args.tool}'. Run with --list to view available tools.")
            sys.exit(1)
        target_tools.append(args.tool)
    elif args.group:
        target_tools = [t_id for t_id, t_def in MOCK_TOOLS.items() if t_def["category"] == args.group]
    elif args.all:
        target_tools = list(MOCK_TOOLS.keys())
    else:
        parser.print_help()
        sys.exit(0)

    print(f"[VESPER EMITTER] Preparing to emit {len(target_tools)} tool call(s)...")

    envelopes_to_send: List[Dict[str, Any]] = []
    for tool_name in target_tools:
        tool_def = MOCK_TOOLS[tool_name]
        latency = random.randint(14, 52)
        print_tool_envelope(tool_name, tool_def, latency)
        if args.to_gateway:
            envelopes_to_send.append(build_websocket_envelope(tool_name, tool_def))

    if args.to_gateway and envelopes_to_send:
        print(f"[VESPER EMITTER] Transmitting {len(envelopes_to_send)} envelope(s) to {args.ws_url}...")
        asyncio.run(emit_over_websocket(args.ws_url, envelopes_to_send, delay=args.delay))


if __name__ == "__main__":
    main()

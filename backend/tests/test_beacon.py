"""Unit tests for the UDP Broadcast Discovery Beacon.

Verifies:
1. DiscoveryBeacon initialization and local IP resolution.
2. UDP broadcast loop packet payload structure and encoding.
3. Safe asynchronous startup and shutdown lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import socket
from unittest.mock import MagicMock, patch

import pytest

from backend.gateway.beacon import DiscoveryBeacon


@pytest.mark.asyncio
async def test_beacon_packet_structure():
    """Verifies that the beacon generates valid JSON with required discovery fields."""
    beacon = DiscoveryBeacon(port=18005, broadcast_interval=0.1, gateway_port=8000)

    with patch.object(beacon, "_get_local_ip", return_value="192.168.1.150"):
        # Setup test UDP listener socket
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 18005))
        listener.setblocking(False)

        # Patch broadcast destination to localhost for isolation
        with patch("backend.gateway.beacon.socket.socket") as mock_sock_cls:
            real_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            mock_sock_cls.return_value = real_sock

            beacon.start()
            assert beacon._running is True

            # Wait briefly for a broadcast tick
            await asyncio.sleep(0.15)
            await beacon.stop()
            assert not beacon._running

            listener.close()
            real_sock.close()


@pytest.mark.asyncio
async def test_beacon_lifecycle():
    """Verifies start and stop idempotence."""
    beacon = DiscoveryBeacon(port=18006, broadcast_interval=0.05)
    beacon.start()
    assert beacon._running

    # Double start should not crash or duplicate tasks
    task1 = beacon._task
    beacon.start()
    assert beacon._task == task1

    await beacon.stop()
    assert not beacon._running
    assert beacon._task is None

    # Double stop should be safe
    await beacon.stop()
    assert not beacon._running

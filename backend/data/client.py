"""VESPER Supabase Client Factory.

Provides a configured Supabase client instance for accessing the cloud database.
Includes resilient DNS caching and fallback (8.8.8.8 / 1.1.1.1 / Anycast) to
gracefully bypass local router/range-extender DNS caching failures.
"""

from __future__ import annotations

import logging
import socket
from typing import Optional
from supabase import Client, create_client

from backend.shared.config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger("vesper.data.supabase")

_supabase_client: Optional[Client] = None
_dns_fallback_installed = False
_dns_cache: dict[str, str] = {
    # Cloudflare Anycast IPs for Supabase edge endpoints
    "mifffaphqqqwodmzjwqb.supabase.co": "104.18.38.10",
}


def _install_dns_fallback() -> None:
    """Installs a transparent fallback and cache to resolve supabase.co."""
    global _dns_fallback_installed
    if _dns_fallback_installed:
        return

    orig_getaddrinfo = socket.getaddrinfo

    def resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # 1. Check in-memory DNS cache first for instant sub-millisecond return
        if isinstance(host, str) and host in _dns_cache:
            return orig_getaddrinfo(_dns_cache[host], port, family, type, proto, flags)

        try:
            return orig_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror:
            if isinstance(host, str) and "supabase.co" in host:
                # Query public DNS (8.8.8.8, 1.1.1.1)
                packet = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
                for part in host.split("."):
                    packet += bytes([len(part)]) + part.encode()
                packet += b"\x00\x00\x01\x00\x01"

                for resolver in ["8.8.8.8", "1.1.1.1"]:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.settimeout(1.5)
                        s.sendto(packet, (resolver, 53))
                        data, _ = s.recvfrom(512)
                        s.close()
                        resolved_ip = ".".join(str(b) for b in data[-4:])
                        _dns_cache[host] = resolved_ip
                        logger.debug(f"[DNS] Resolved '{host}' via {resolver}: {resolved_ip}")
                        return orig_getaddrinfo(resolved_ip, port, family, type, proto, flags)
                    except Exception:
                        continue

                # Fallback to Supabase Anycast Edge IP
                fallback_ip = "104.18.38.10"
                _dns_cache[host] = fallback_ip
                return orig_getaddrinfo(fallback_ip, port, family, type, proto, flags)
            raise

    socket.getaddrinfo = resilient_getaddrinfo
    _dns_fallback_installed = True


def get_supabase_client() -> Client:
    """Returns the singleton Supabase client, initializing it if necessary."""
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be configured in environment (.env). "
            "Please configure your Supabase credentials."
        )

    _install_dns_fallback()
    logger.info(f"[SUPABASE] Connecting to Supabase project at '{SUPABASE_URL}'")
    _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def reset_client() -> None:
    """Resets the singleton instance (useful for testing)."""
    global _supabase_client
    _supabase_client = None

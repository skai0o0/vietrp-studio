"""Real client IP behind Cloudflare Tunnel."""

from __future__ import annotations

import ipaddress
from collections.abc import Collection

UNKNOWN_PEER = "unknown"


def resolve_client_ip(peer: str | None, cf_connecting_ip: str | None, trusted_hosts: Collection[str]) -> str:
    """Trust `CF-Connecting-IP` only when the TCP peer is a trusted proxy (cloudflared on loopback)."""
    peer_ip = peer or UNKNOWN_PEER
    if peer_ip in trusted_hosts and cf_connecting_ip:
        try:
            return str(ipaddress.ip_address(cf_connecting_ip.strip()))
        except ValueError:
            return peer_ip
    return peer_ip

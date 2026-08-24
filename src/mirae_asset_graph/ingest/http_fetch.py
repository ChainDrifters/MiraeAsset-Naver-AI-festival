"""Bounded, redirect-aware HTTP reads for approved source URLs."""

from __future__ import annotations

import urllib.error
import urllib.request
import ipaddress
import socket
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol
from urllib.parse import urljoin
from urllib.parse import urlsplit

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5


class _Response(Protocol):
    def read(self) -> bytes: ...
    def geturl(self) -> str: ...
    def __enter__(self) -> _Response: ...
    def __exit__(self, *args: object) -> object: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _open_once(request: urllib.request.Request, timeout: float) -> _Response:
    opener = urllib.request.build_opener(_NoRedirect())
    return opener.open(request, timeout=timeout)


def _resolve_host(host: str, port: int) -> Sequence[tuple[object, ...]]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def validate_dns_destination(url: str) -> tuple[str, ...]:
    parsed = urlsplit(url)
    if not parsed.hostname:
        raise ValueError("source URL has no DNS hostname")
    addresses: set[str] = set()
    for result in _resolve_host(parsed.hostname, parsed.port or 443):
        sockaddr = result[4]
        if not isinstance(sockaddr, tuple) or not sockaddr:
            continue
        address = str(sockaddr[0])
        ip = ipaddress.ip_address(address)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or not ip.is_global
        ):
            raise ValueError(f"source DNS resolved to a blocked address: {address}")
        addresses.add(ip.compressed)
    if not addresses:
        raise ValueError("source DNS resolution returned no usable addresses")
    return tuple(sorted(addresses))


def read_with_validated_redirects(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    validate_url: Callable[[str], str],
) -> bytes:
    current = validate_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        _ = validate_dns_destination(current)
        request = urllib.request.Request(current, headers=dict(headers), method="GET")
        try:
            with _open_once(request, timeout) as response:
                final_url = validate_url(response.geturl())
                if final_url != current:
                    raise ValueError("unexpected unvalidated redirect destination")
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in _REDIRECT_CODES:
                raise
            if redirect_count >= MAX_REDIRECTS:
                raise ValueError(f"source redirect limit exceeded ({MAX_REDIRECTS})") from error
            location = error.headers.get("Location")
            if not location:
                raise ValueError("source redirect is missing Location") from error
            current = validate_url(urljoin(current, location))
    raise AssertionError("redirect loop always returns or raises")

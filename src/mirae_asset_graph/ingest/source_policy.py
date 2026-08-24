"""Positive URL policy shared by target parsing and network adapters."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SEC_HOSTS = frozenset({"www.sec.gov", "data.sec.gov"})
_CREDENTIAL_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "access_token",
        "auth",
        "authorization",
        "credential",
        "api_key",
        "apikey",
        "api-key",
        "x-api-key",
        "secret",
        "signature",
        "sig",
        "key",
    }
)


def normalize_host(value: str) -> str:
    host = value.rstrip(".").casefold()
    if not host:
        raise ValueError("source URL host is empty")
    try:
        normalized = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("source URL host is not valid IDNA") from error
    try:
        ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        pass
    else:
        raise ValueError("source URL IP literals are blocked")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise ValueError("source URL localhost is blocked")
    return normalized


def normalize_reviewed_hosts(hosts: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({normalize_host(host) for host in hosts}))
    if not normalized:
        raise ValueError("manager source requires at least one reviewed manager host")
    for host in normalized:
        if host == "krx.co.kr" or host.endswith(".krx.co.kr"):
            raise ValueError("KRX automated acquisition is blocked by source policy")
    return normalized


def validate_source_url(
    source: str,
    url: str,
    *,
    manager_hosts: Iterable[str] = (),
    allow_test_hosts: bool = False,
) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL userinfo is blocked")
    host = normalize_host(parsed.hostname)
    if host == "krx.co.kr" or host.endswith(".krx.co.kr"):
        raise ValueError("KRX automated acquisition is blocked by source policy")
    if host == "example.invalid" and not allow_test_hosts:
        raise ValueError("example.invalid is test-only")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.casefold() in _CREDENTIAL_KEYS for key, _value in query):
        raise ValueError("credential-like source URL query parameter is blocked")

    if allow_test_hosts and host == "example.invalid":
        allowed = True
    elif source == "sec_nport":
        allowed = host in SEC_HOSTS
    elif source == "manager_basket":
        allowed = host in normalize_reviewed_hosts(manager_hosts)
    else:
        raise ValueError(f"unsupported source policy: {source}")
    if not allowed:
        if source == "manager_basket":
            raise ValueError(f"source URL host is not a reviewed manager host: {host}")
        raise ValueError(f"source URL host is not an official SEC host: {host}")
    netloc = host + (f":{parsed.port}" if parsed.port is not None else "")
    return urlunsplit(("https", netloc, parsed.path or "/", urlencode(query), ""))

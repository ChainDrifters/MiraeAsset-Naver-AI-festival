from __future__ import annotations

import pytest
import email.message
import urllib.error
import urllib.request
import socket

import mirae_asset_graph.ingest.http_fetch as http_fetch
from mirae_asset_graph.ingest.http_fetch import read_with_validated_redirects
from mirae_asset_graph.ingest.source_policy import validate_source_url


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/private",
        "https://10.0.0.1/private",
        "https://localhost/private",
        "https://user:pass@www.sec.gov/file.xml",
        "https://www.sec.gov/file.xml?token=secret",
        "https://www.sec.gov.evil.example/file.xml",
        "https://global.krx.co.kr./file.xml",
    ],
)
def test_sec_policy_rejects_untrusted_or_credential_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_source_url("sec_nport", url)


def test_sec_policy_normalizes_trailing_dot_and_idna() -> None:
    assert validate_source_url("sec_nport", "https://WWW.SEC.GOV./file.xml") == (
        "https://www.sec.gov/file.xml"
    )


def test_manager_policy_requires_explicit_reviewed_host() -> None:
    assert validate_source_url(
        "manager_basket",
        "https://holdings.manager.example/file.csv",
        manager_hosts=("holdings.manager.example",),
    ) == "https://holdings.manager.example/file.csv"
    with pytest.raises(ValueError, match="reviewed manager host"):
        validate_source_url(
            "manager_basket",
            "https://cdn.manager.example/file.csv",
            manager_hosts=("holdings.manager.example",),
        )


def test_redirect_to_krx_is_rejected_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def redirect(request: urllib.request.Request, timeout: float):
        calls.append(request.full_url)
        headers = email.message.Message()
        headers["Location"] = "https://global.krx.co.kr./blocked.csv"
        raise urllib.error.HTTPError(request.full_url, 302, "redirect", headers, None)

    monkeypatch.setattr(http_fetch, "_open_once", redirect)
    monkeypatch.setattr(
        http_fetch,
        "_resolve_host",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
    )
    with pytest.raises(ValueError, match="KRX automated acquisition"):
        read_with_validated_redirects(
            "https://www.sec.gov/file.xml",
            headers={},
            timeout=1,
            validate_url=lambda url: validate_source_url("sec_nport", url),
        )
    assert calls == ["https://www.sec.gov/file.xml"]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "fe80::1"])
def test_fetch_dns_rejects_non_public_ipv4_and_ipv6(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    monkeypatch.setattr(
        http_fetch,
        "_resolve_host",
        lambda host, port: [(family, socket.SOCK_STREAM, 6, "", sockaddr)],
    )
    with pytest.raises(ValueError, match="blocked address"):
        http_fetch.validate_dns_destination("https://www.sec.gov/file.xml")


def test_fetch_dns_accepts_public_ipv4_and_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http_fetch,
        "_resolve_host",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", port, 0, 0)),
        ],
    )
    assert http_fetch.validate_dns_destination("https://www.sec.gov/file.xml") == (
        "2606:2800:220:1:248:1893:25c8:1946",
        "93.184.216.34",
    )

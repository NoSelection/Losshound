from datetime import datetime

import pytest

from losshound.core.alerts import AlertEvent
from losshound.core.config import AlertsConfig
from losshound.core.notifications import (
    format_discord_payload,
    format_generic_payload,
)


def _event(severity: str = "warning", is_resolution: bool = False) -> AlertEvent:
    return AlertEvent(
        timestamp=datetime(2026, 5, 11, 18, 42, 13),
        category="lan_issue",
        severity=severity,
        title="Lan Issue",
        message="Gateway 192.168.1.1 is unreachable.",
        is_resolution=is_resolution,
    )


# -- Discord payload -----------------------------------------------

def test_format_discord_payload_basic():
    payload = format_discord_payload(_event(severity="warning"))

    assert "embeds" in payload
    assert isinstance(payload["embeds"], list)
    assert len(payload["embeds"]) == 1

    embed = payload["embeds"][0]
    assert embed["title"] == "Losshound — Lan Issue"
    assert "Gateway 192.168.1.1 is unreachable." in embed["description"]
    assert embed["timestamp"] == "2026-05-11T18:42:13"
    assert embed["color"] == 0xf9e2af  # warning -> yellow
    assert "warning" in embed["footer"]["text"]


def test_format_discord_payload_critical_is_red():
    payload = format_discord_payload(_event(severity="critical"))
    assert payload["embeds"][0]["color"] == 0xf38ba8


def test_format_discord_payload_resolution_is_blue():
    payload = format_discord_payload(
        _event(severity="info", is_resolution=True)
    )
    assert payload["embeds"][0]["color"] == 0x89b4fa


# -- Generic payload -----------------------------------------------

def test_format_generic_payload_basic():
    payload = format_generic_payload(_event(severity="warning"))

    assert payload["source"] == "losshound"
    assert payload["timestamp"] == "2026-05-11T18:42:13"
    assert payload["category"] == "lan_issue"
    assert payload["severity"] == "warning"
    assert payload["title"] == "Lan Issue"
    assert payload["message"] == "Gateway 192.168.1.1 is unreachable."
    assert payload["is_resolution"] is False


def test_format_generic_payload_resolution():
    payload = format_generic_payload(
        _event(severity="info", is_resolution=True)
    )
    assert payload["is_resolution"] is True
    assert payload["severity"] == "info"


# -- post_webhook --------------------------------------------------

def test_post_webhook_returns_true_on_2xx(monkeypatch):
    from losshound.core.notifications import post_webhook
    captured = {}

    class _FakeResponse:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b""

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    ok = post_webhook("https://example.com/h", {"hello": "world"}, timeout=5)
    assert ok is True
    assert captured["url"] == "https://example.com/h"
    assert b'"hello"' in captured["data"]
    assert captured["timeout"] == 5


def test_post_webhook_returns_false_on_http_error(monkeypatch):
    from losshound.core.notifications import post_webhook
    import urllib.error

    def _fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 500, "Server Error", {}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    ok = post_webhook("https://example.com/h", {})
    assert ok is False


def test_post_webhook_returns_false_on_url_error(monkeypatch):
    from losshound.core.notifications import post_webhook
    import urllib.error

    def _fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    ok = post_webhook("https://example.com/h", {})
    assert ok is False


def test_post_webhook_returns_false_on_unexpected_exception(monkeypatch):
    from losshound.core.notifications import post_webhook

    def _fake_urlopen(req, timeout=None):
        raise RuntimeError("something weird")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    ok = post_webhook("https://example.com/h", {})
    assert ok is False

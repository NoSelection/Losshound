"""Webhook notification dispatcher."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Optional

from losshound.core.alerts import AlertEvent
from losshound.core.config import AlertsConfig

logger = logging.getLogger(__name__)


_SEVERITY_COLORS = {
    "info":     0x89b4fa,  # blue (resolution)
    "warning":  0xf9e2af,  # yellow
    "critical": 0xf38ba8,  # red
}


def format_discord_payload(event: AlertEvent) -> dict:
    """Build a Discord webhook payload with a colored embed."""
    color = _SEVERITY_COLORS.get(event.severity, 0x6c7086)
    return {
        "embeds": [{
            "title": f"Losshound — {event.title}",
            "description": event.message,
            "color": color,
            "timestamp": event.timestamp.isoformat(),
            "footer": {"text": f"Severity: {event.severity}"},
        }]
    }


def format_generic_payload(event: AlertEvent) -> dict:
    """Build a generic JSON payload — flat dict with all event fields.

    Stable contract: fields only get added in future versions, never
    renamed or removed.
    """
    return {
        "source": "losshound",
        "timestamp": event.timestamp.isoformat(),
        "category": event.category,
        "severity": event.severity,
        "title": event.title,
        "message": event.message,
        "is_resolution": event.is_resolution,
    }


def post_webhook(url: str, payload: dict, timeout: float = 10.0) -> bool:
    """POST ``payload`` as JSON to ``url``. Returns True on 2xx.

    Catches all exceptions and logs them. Never raises — callers that
    fire-and-forget can ignore the return value.
    """
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Losshound/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 0)
            return 200 <= status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("Webhook POST returned %s for %s", exc.code, url)
        return False
    except urllib.error.URLError as exc:
        logger.warning("Webhook POST failed (network): %s", exc)
        return False
    except Exception:
        logger.exception("Webhook POST raised unexpectedly")
        return False

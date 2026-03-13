from __future__ import annotations

import logging
import socket
import time
from datetime import datetime
from typing import Optional

from losshound.core.models import DnsResult

logger = logging.getLogger(__name__)


def check_dns(hostname: str, timeout: float = 5.0) -> DnsResult:
    """Test DNS resolution for a hostname and measure timing."""
    now = datetime.now()
    old_timeout = socket.getdefaulttimeout()

    try:
        socket.setdefaulttimeout(timeout)
        start = time.perf_counter()
        results = socket.getaddrinfo(hostname, None, socket.AF_INET)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if results:
            resolved_ip = results[0][4][0]
            logger.debug("DNS %s -> %s (%.1f ms)", hostname, resolved_ip, elapsed_ms)
            return DnsResult(
                hostname=hostname,
                timestamp=now,
                resolved=True,
                resolved_ip=resolved_ip,
                resolution_time_ms=elapsed_ms,
            )
        else:
            return DnsResult(
                hostname=hostname,
                timestamp=now,
                resolved=False,
                error="No results returned",
            )
    except socket.gaierror as exc:
        logger.debug("DNS %s failed: %s", hostname, exc)
        return DnsResult(
            hostname=hostname,
            timestamp=now,
            resolved=False,
            error=str(exc),
        )
    except socket.timeout:
        return DnsResult(
            hostname=hostname,
            timestamp=now,
            resolved=False,
            error="DNS resolution timed out",
        )
    except OSError as exc:
        return DnsResult(
            hostname=hostname,
            timestamp=now,
            resolved=False,
            error=str(exc),
        )
    finally:
        socket.setdefaulttimeout(old_timeout)

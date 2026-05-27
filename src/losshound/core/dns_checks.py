from __future__ import annotations

import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime

from losshound.core.models import DnsResult

logger = logging.getLogger(__name__)


def check_dns(hostname: str, timeout: float = 5.0) -> DnsResult:
    """Test DNS resolution for a hostname and measure timing."""
    now = datetime.now()

    def _resolve():
        return socket.getaddrinfo(hostname, None, socket.AF_INET)

    start = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_resolve)
        try:
            results = future.result(timeout=timeout)
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
        except (TimeoutError, socket.timeout):
            future.cancel()
            return DnsResult(
                hostname=hostname,
                timestamp=now,
                resolved=False,
                error="DNS resolution timed out",
            )
        except socket.gaierror as exc:
            logger.debug("DNS %s failed: %s", hostname, exc)
            return DnsResult(
                hostname=hostname,
                timestamp=now,
                resolved=False,
                error=str(exc),
            )
        except OSError as exc:
            return DnsResult(
                hostname=hostname,
                timestamp=now,
                resolved=False,
                error=str(exc),
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

from __future__ import annotations

import logging
import re
import statistics
import subprocess
from datetime import datetime
from typing import Optional

from losshound.core.models import PingResult

logger = logging.getLogger(__name__)

# Regexes for English Windows ping output
_RE_STATS = re.compile(
    r"Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+),\s*Lost\s*=\s*(\d+)\s*\((\d+)%"
)
_RE_RTT = re.compile(
    r"Minimum\s*=\s*(\d+)ms,\s*Maximum\s*=\s*(\d+)ms,\s*Average\s*=\s*(\d+)ms"
)
_RE_REPLY_TIME = re.compile(r"time[=<](\d+)ms")


def ping(target: str, count: int = 4, timeout_ms: int = 2000) -> PingResult:
    """Run a subprocess ping and parse the results."""
    now = datetime.now()
    cmd = f'chcp 437 >nul && ping -n {count} -w {timeout_ms} {target}'
    process_timeout = (count * timeout_ms / 1000) + 10

    try:
        result = subprocess.run(
            ["cmd", "/c", cmd],
            capture_output=True, text=True,
            timeout=process_timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        return PingResult(
            target=target, timestamp=now,
            packets_sent=count, packets_received=0,
            loss_percent=100.0, timed_out=True,
            error="Process timed out",
        )
    except OSError as exc:
        return PingResult(
            target=target, timestamp=now,
            packets_sent=count, packets_received=0,
            loss_percent=100.0, timed_out=True,
            error=str(exc),
        )

    return _parse_ping_output(output, target, now, count)


def _parse_ping_output(
    output: str, target: str, timestamp: datetime, count: int
) -> PingResult:
    """Parse Windows ping output into a PingResult."""
    sent, received, loss_pct = count, 0, 100.0
    rtt_min: Optional[float] = None
    rtt_avg: Optional[float] = None
    rtt_max: Optional[float] = None
    jitter: Optional[float] = None

    stats_match = _RE_STATS.search(output)
    if stats_match:
        sent = int(stats_match.group(1))
        received = int(stats_match.group(2))
        loss_pct = float(stats_match.group(4))

    rtt_match = _RE_RTT.search(output)
    if rtt_match:
        rtt_min = float(rtt_match.group(1))
        rtt_max = float(rtt_match.group(2))
        rtt_avg = float(rtt_match.group(3))

    # Extract per-packet RTT for jitter calculation
    per_packet = [float(m) for m in _RE_REPLY_TIME.findall(output)]
    if len(per_packet) >= 2:
        diffs = [abs(per_packet[i+1] - per_packet[i]) for i in range(len(per_packet)-1)]
        jitter = statistics.mean(diffs)

    timed_out = received == 0

    return PingResult(
        target=target,
        timestamp=timestamp,
        packets_sent=sent,
        packets_received=received,
        loss_percent=loss_pct,
        rtt_min=rtt_min,
        rtt_avg=rtt_avg,
        rtt_max=rtt_max,
        rtt_jitter=jitter,
        timed_out=timed_out,
    )

"""Connectivity drop analyzer — rapid polling to diagnose intermittent outages.

Works on both Ethernet and WiFi.  Rapidly polls gateway + WAN reachability,
checks NIC link state, and queries Windows event logs to classify drops as:

- Ethernet link flap (cable/NIC/switch issue)
- Router/gateway failure (router crash/reboot cycle)
- ISP/WAN outage (gateway ok, internet dead)
- DNS-only outage (internet ok, DNS failing)
- Full outage (everything down — could be ISP, modem, or power)

On WiFi connections, additionally correlates with signal strength to detect
possible RF interference or deauth attacks.

Uses ``netsh``, ``ping``, and ``wevtutil``.  No admin required for basic
monitoring; admin recommended for full event-log access.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_CREATE_NO_WINDOW: int = 0x08000000


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ConnSample:
    """A single point-in-time connectivity sample."""

    timestamp: datetime
    # Link layer
    link_up: bool                     # NIC has link (media connected)
    connection_type: str              # "ethernet" or "wifi"
    speed_mbps: float                 # negotiated link speed
    # WiFi-specific (0/empty for Ethernet)
    wifi_signal_pct: int
    wifi_ssid: str
    wifi_channel: int
    # Gateway
    gateway_reachable: bool
    gateway_rtt_ms: Optional[float]
    # WAN (public IP)
    wan_reachable: bool
    wan_rtt_ms: Optional[float]
    # DNS
    dns_ok: bool


@dataclass
class NetworkEvent:
    """An event extracted from Windows event logs."""

    timestamp: datetime
    source: str                       # "NDIS", "WLAN", "DHCP", "Tcpip", etc.
    event_id: int
    description: str


@dataclass
class DropEpisode:
    """A detected connectivity drop episode."""

    start: datetime
    end: Optional[datetime]
    duration_seconds: float
    samples: int
    gateway_lost: bool
    wan_lost: bool
    dns_lost: bool
    link_lost: bool
    wifi_signal_dropped: bool         # WiFi only
    pattern: str                      # classification label


@dataclass
class DropAnalysisReport:
    """Full drop analysis report."""

    scan_duration_seconds: float
    connection_type: str
    total_samples: int
    samples: list[ConnSample]
    drops: list[DropEpisode]
    events: list[NetworkEvent]
    verdict: str
    confidence: str
    details: list[str]
    recommendations: list[str]
    drop_regularity: Optional[str]    # "regular ~Xmin", "irregular", None


# ---------------------------------------------------------------------------
# Helpers — quick single-packet probes
# ---------------------------------------------------------------------------

def _quick_ping(target: str, timeout_ms: int = 1500) -> tuple[bool, Optional[float]]:
    """Send a single ping and return (reachable, rtt_ms)."""
    try:
        proc = subprocess.run(
            ["cmd", "/c", f"chcp 437 >nul && ping -n 1 -w {timeout_ms} {target}"],
            capture_output=True, text=True, timeout=(timeout_ms / 1000) + 3,
            creationflags=_CREATE_NO_WINDOW,
        )
        out = proc.stdout
        if "TTL=" in out or "ttl=" in out:
            m = re.search(r"time[=<](\d+)ms", out)
            rtt = float(m.group(1)) if m else 0.0
            return True, rtt
        return False, None
    except Exception:
        return False, None


def _quick_dns(hostname: str = "google.com") -> bool:
    """Attempt a quick DNS lookup via nslookup."""
    try:
        proc = subprocess.run(
            ["cmd", "/c", f"chcp 437 >nul && nslookup {hostname}"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        return "Address" in proc.stdout and proc.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NIC link state
# ---------------------------------------------------------------------------

def _get_active_nic_info() -> tuple[str, bool, float]:
    """Detect connection type, link state, and speed from netsh.

    Returns (connection_type, link_up, speed_mbps).
    """
    try:
        proc = subprocess.run(
            ["cmd", "/c", "chcp 437 >nul && netsh interface show interface"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1].lower() == "connected":
                iface_type = parts[2].lower()  # "dedicated" (ethernet) or other
                name = " ".join(parts[3:])
                is_ethernet = "wi-fi" not in name.lower() and "wireless" not in name.lower()
                conn_type = "ethernet" if is_ethernet else "wifi"

                # Get speed
                speed = _get_link_speed(name)
                return conn_type, True, speed

        # Check for disconnected interfaces
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1].lower() == "disconnected":
                name = " ".join(parts[3:])
                is_ethernet = "wi-fi" not in name.lower() and "wireless" not in name.lower()
                conn_type = "ethernet" if is_ethernet else "wifi"
                return conn_type, False, 0.0

    except Exception as exc:
        logger.debug("NIC info failed: %s", exc)

    return "unknown", False, 0.0


def _get_link_speed(interface_name: str) -> float:
    """Get the negotiated link speed for a network interface."""
    try:
        proc = subprocess.run(
            ["cmd", "/c", f'chcp 437 >nul && netsh interface ipv4 show subinterfaces'],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        for line in proc.stdout.splitlines():
            if interface_name.lower() in line.lower():
                # Format: MTU  MediaSenseState   Bytes In  Bytes Out  Interface
                # Look for link speed from wmic instead
                break
    except Exception:
        pass

    # Fallback: wmic
    try:
        proc = subprocess.run(
            ["cmd", "/c", "chcp 437 >nul && wmic nic where NetEnabled=true get Name,Speed /format:csv"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            # CSV format: Node,Name,Speed
            parts = line.split(",")
            if len(parts) >= 3:
                try:
                    speed_bps = int(parts[-1].strip())
                    return speed_bps / 1_000_000  # Convert to Mbps
                except ValueError:
                    continue
    except Exception:
        pass

    return 0.0


def _check_media_status() -> bool:
    """Check if the Ethernet cable is physically connected (media sense)."""
    try:
        proc = subprocess.run(
            ["cmd", "/c", "chcp 437 >nul && ipconfig /all"],
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        # If "Media disconnected" appears, the cable is unplugged
        return "Media disconnected" not in proc.stdout
    except Exception:
        return True  # assume connected on error


# ---------------------------------------------------------------------------
# Windows event logs
# ---------------------------------------------------------------------------

def _get_network_events(hours: int = 3) -> list[NetworkEvent]:
    """Query Windows event logs for network-related events.

    Sources checked:
    - Microsoft-Windows-NDIS (link up/down)
    - Microsoft-Windows-WLAN-AutoConfig (WiFi connect/disconnect)
    - Microsoft-Windows-Dhcp-Client (DHCP issues)
    - Microsoft-Windows-NetworkProfile (network changes)
    """
    events: list[NetworkEvent] = []
    ms = hours * 3600 * 1000

    log_queries = [
        # (log_name, source_label, interesting_event_ids)
        ("System", "NDIS/Tcpip", None),  # Network adapter events
        ("Microsoft-Windows-WLAN-AutoConfig/Operational", "WLAN", {8001, 8002, 8003}),
    ]

    # System log — look for network adapter events
    try:
        cmd = (
            f'wevtutil qe System '
            f'/q:"*[System[TimeCreated[timediff(@SystemTime) <= {ms}] '
            f'and (Provider[@Name=\'Microsoft-Windows-NDIS\'] '
            f'or Provider[@Name=\'Tcpip\'] '
            f'or Provider[@Name=\'e1dexpress\'] '
            f'or Provider[@Name=\'Microsoft-Windows-DHCPv4-Client\'] '
            f'or Provider[@Name=\'Microsoft-Windows-Dhcp-Client\'] '
            f'or Provider[@Name=\'Dhcp\']'
            f')]]" '
            f'/c:50 /rd:true /f:text'
        )
        proc = subprocess.run(
            ["cmd", "/c", f"chcp 437 >nul && {cmd}"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode == 0:
            events.extend(_parse_wevtutil_text(proc.stdout, "System"))
    except Exception as exc:
        logger.debug("System event log query failed: %s", exc)

    # WLAN log
    try:
        cmd = (
            f'wevtutil qe "Microsoft-Windows-WLAN-AutoConfig/Operational" '
            f'/q:"*[System[TimeCreated[timediff(@SystemTime) <= {ms}]]]" '
            f'/c:50 /rd:true /f:text'
        )
        proc = subprocess.run(
            ["cmd", "/c", f"chcp 437 >nul && {cmd}"],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode == 0:
            events.extend(_parse_wevtutil_text(proc.stdout, "WLAN"))
    except Exception as exc:
        logger.debug("WLAN event log query failed: %s", exc)

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    return events


def _parse_wevtutil_text(output: str, source_label: str) -> list[NetworkEvent]:
    """Parse wevtutil /f:text output into NetworkEvent objects."""
    events: list[NetworkEvent] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                evt = _build_network_event(current, source_label)
                if evt:
                    events.append(evt)
                current = {}
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            current[key.strip().lower()] = val.strip()
        elif current:
            last_key = list(current.keys())[-1]
            current[last_key] += " " + stripped

    if current:
        evt = _build_network_event(current, source_label)
        if evt:
            events.append(evt)

    return events


def _build_network_event(fields: dict[str, str], source_label: str) -> Optional[NetworkEvent]:
    """Build a NetworkEvent from parsed wevtutil fields."""
    try:
        eid_str = fields.get("event id", "0")
        m = re.search(r"(\d+)", eid_str)
        event_id = int(m.group(1)) if m else 0

        ts_str = fields.get("date", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.replace("T", " ").split(".")[0])
        except (ValueError, IndexError):
            timestamp = datetime.now()

        desc = fields.get("description", "")
        if not desc:
            # Build description from provider + event ID
            provider = fields.get("source", fields.get("provider", ""))
            desc = f"{provider} Event {event_id}"

        return NetworkEvent(
            timestamp=timestamp,
            source=source_label,
            event_id=event_id,
            description=desc[:120],
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# WiFi state (reuses wifi_diag module when available)
# ---------------------------------------------------------------------------

def _get_wifi_state() -> tuple[bool, int, str, int]:
    """Get WiFi state: (connected, signal_pct, ssid, channel)."""
    try:
        from losshound.core.wifi_diag import get_wifi_interface
        iface = get_wifi_interface()
        if iface and iface.state == "connected":
            return True, iface.signal_pct, iface.ssid, iface.channel
        return False, 0, "", 0
    except Exception:
        return False, 0, "", 0


# ---------------------------------------------------------------------------
# Core monitoring loop
# ---------------------------------------------------------------------------

def run_drop_analysis(
    gateway: str,
    wan_target: str = "8.8.8.8",
    duration_seconds: int = 120,
    poll_interval: float = 3.0,
    progress_callback=None,
) -> DropAnalysisReport:
    """Run rapid connectivity polling to catch and classify drop events.

    Args:
        gateway: Gateway IP to ping.
        wan_target: Public IP to ping for WAN check.
        duration_seconds: How long to monitor.
        poll_interval: Seconds between samples.
        progress_callback: Optional callable for status updates.
    """
    samples: list[ConnSample] = []
    start_time = time.monotonic()
    end_time = start_time + duration_seconds
    sample_num = 0
    detected_conn_type = "unknown"

    if progress_callback:
        progress_callback(
            f"Monitoring for {duration_seconds}s (polling every {poll_interval:.0f}s)..."
        )
        progress_callback(f"  Gateway: {gateway}  |  WAN target: {wan_target}")

    while time.monotonic() < end_time:
        sample_num += 1
        now = datetime.now()

        # NIC link state
        conn_type, link_up, speed = _get_active_nic_info()
        if conn_type != "unknown":
            detected_conn_type = conn_type

        # WiFi state (only if on WiFi)
        wifi_sig, wifi_ssid, wifi_ch = 0, "", 0
        if conn_type == "wifi":
            _, wifi_sig, wifi_ssid, wifi_ch = _get_wifi_state()

        # Gateway ping
        gw_ok, gw_rtt = _quick_ping(gateway)

        # WAN ping
        wan_ok, wan_rtt = _quick_ping(wan_target)

        # Quick DNS (less frequent — every 5th sample to avoid hammering)
        dns_ok = True
        if sample_num % 5 == 1:
            dns_ok = _quick_dns()

        sample = ConnSample(
            timestamp=now,
            link_up=link_up,
            connection_type=conn_type,
            speed_mbps=speed,
            wifi_signal_pct=wifi_sig,
            wifi_ssid=wifi_ssid,
            wifi_channel=wifi_ch,
            gateway_reachable=gw_ok,
            gateway_rtt_ms=gw_rtt,
            wan_reachable=wan_ok,
            wan_rtt_ms=wan_rtt,
            dns_ok=dns_ok,
        )
        samples.append(sample)

        if progress_callback and sample_num % 5 == 0:
            elapsed = time.monotonic() - start_time
            remaining = max(0, duration_seconds - elapsed)
            gw_str = f"{gw_rtt:.0f}ms" if gw_ok and gw_rtt else ("OK" if gw_ok else "LOST")
            wan_str = f"{wan_rtt:.0f}ms" if wan_ok and wan_rtt else ("OK" if wan_ok else "LOST")
            link_str = f"{speed:.0f}Mbps" if link_up else "DOWN"
            progress_callback(
                f"  [{elapsed:3.0f}s/{duration_seconds}s] "
                f"Link:{link_str}  GW:{gw_str}  WAN:{wan_str}  "
                f"({remaining:.0f}s left)"
            )

        # Sleep until next poll
        target_time = (sample_num * poll_interval)
        while (time.monotonic() - start_time) < target_time:
            if time.monotonic() >= end_time:
                break
            time.sleep(0.2)

    actual_duration = time.monotonic() - start_time

    # Grab event logs
    events = _get_network_events(hours=3)

    # Analyze
    drops = _detect_drops(samples)
    regularity = _check_regularity(drops)
    verdict, confidence, details, recs = _analyze(
        samples, drops, events, detected_conn_type, regularity
    )

    return DropAnalysisReport(
        scan_duration_seconds=actual_duration,
        connection_type=detected_conn_type,
        total_samples=len(samples),
        samples=samples,
        drops=drops,
        events=events,
        verdict=verdict,
        confidence=confidence,
        details=details,
        recommendations=recs,
        drop_regularity=regularity,
    )


# ---------------------------------------------------------------------------
# Drop detection
# ---------------------------------------------------------------------------

def _detect_drops(samples: list[ConnSample]) -> list[DropEpisode]:
    """Identify episodes where connectivity was lost."""
    drops: list[DropEpisode] = []
    in_drop = False
    start_idx = 0

    for i, s in enumerate(samples):
        is_bad = not s.gateway_reachable or not s.wan_reachable or not s.link_up

        if is_bad and not in_drop:
            in_drop = True
            start_idx = i
        elif not is_bad and in_drop:
            in_drop = False
            drops.append(_build_drop(samples, start_idx, i - 1))

    if in_drop:
        drops.append(_build_drop(samples, start_idx, len(samples) - 1))

    return drops


def _build_drop(samples: list[ConnSample], start_idx: int, end_idx: int) -> DropEpisode:
    """Build a DropEpisode from sample index range."""
    episode = samples[start_idx:end_idx + 1]
    start_ts = episode[0].timestamp
    end_ts = episode[-1].timestamp
    duration = (end_ts - start_ts).total_seconds()

    gw_lost = any(not s.gateway_reachable for s in episode)
    wan_lost = any(not s.wan_reachable for s in episode)
    dns_lost = any(not s.dns_ok for s in episode)
    link_lost = any(not s.link_up for s in episode)

    # WiFi signal analysis
    wifi_dropped = False
    if any(s.connection_type == "wifi" for s in episode):
        pre_sig = samples[max(0, start_idx - 1)].wifi_signal_pct
        min_sig = min(s.wifi_signal_pct for s in episode)
        wifi_dropped = pre_sig > 30 and min_sig < pre_sig * 0.4

    # Classify
    if link_lost:
        pattern = "link_flap"
    elif gw_lost and wan_lost:
        if wifi_dropped:
            pattern = "rf_interference"
        else:
            pattern = "full_outage"
    elif not gw_lost and wan_lost:
        pattern = "isp_wan_issue"
    elif gw_lost and not wan_lost:
        pattern = "gateway_issue"
    elif dns_lost:
        pattern = "dns_issue"
    else:
        pattern = "unknown"

    return DropEpisode(
        start=start_ts,
        end=end_ts,
        duration_seconds=duration,
        samples=len(episode),
        gateway_lost=gw_lost,
        wan_lost=wan_lost,
        dns_lost=dns_lost,
        link_lost=link_lost,
        wifi_signal_dropped=wifi_dropped,
        pattern=pattern,
    )


# ---------------------------------------------------------------------------
# Regularity detection
# ---------------------------------------------------------------------------

def _check_regularity(drops: list[DropEpisode]) -> Optional[str]:
    """Check if drops happen at regular intervals."""
    if len(drops) < 3:
        return None

    gaps = []
    for i in range(1, len(drops)):
        gap = (drops[i].start - drops[i - 1].start).total_seconds()
        gaps.append(gap)

    if not gaps:
        return None

    avg_gap = sum(gaps) / len(gaps)
    max_deviation = max(abs(g - avg_gap) for g in gaps)

    # If all gaps are within 20% of the average, it's regular
    if avg_gap > 0 and max_deviation / avg_gap < 0.20:
        minutes = avg_gap / 60
        return f"regular ~{minutes:.0f}min intervals"

    return "irregular"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze(
    samples: list[ConnSample],
    drops: list[DropEpisode],
    events: list[NetworkEvent],
    conn_type: str,
    regularity: Optional[str],
) -> tuple[str, str, list[str], list[str]]:
    """Produce verdict, confidence, details, and recommendations."""
    details: list[str] = []
    recs: list[str] = []

    if not samples:
        return "Insufficient data", "low", ["No samples collected"], []

    total = len(samples)
    span = samples[-1].timestamp - samples[0].timestamp
    gw_fails = sum(1 for s in samples if not s.gateway_reachable)
    wan_fails = sum(1 for s in samples if not s.wan_reachable)
    link_fails = sum(1 for s in samples if not s.link_up)
    dns_fails = sum(1 for s in samples if not s.dns_ok)

    details.append(f"Connection type: {conn_type}")
    details.append(f"Collected {total} samples over {span}")
    details.append(f"Gateway failures: {gw_fails}/{total} ({gw_fails/total*100:.0f}%)")
    details.append(f"WAN failures: {wan_fails}/{total} ({wan_fails/total*100:.0f}%)")
    details.append(f"Link failures: {link_fails}/{total}")
    details.append(f"DNS failures: {dns_fails}/{total}")
    details.append(f"Drop episodes: {len(drops)}")
    if regularity:
        details.append(f"Drop pattern: {regularity}")

    # Count event log entries by type
    ndis_events = [e for e in events if e.source == "System"]
    wlan_events = [e for e in events if e.source == "WLAN"]
    if ndis_events:
        details.append(f"System network events (last 3h): {len(ndis_events)}")
    if wlan_events:
        details.append(f"WLAN events (last 3h): {len(wlan_events)}")

    # Classify drops
    link_flaps = [d for d in drops if d.pattern == "link_flap"]
    full_outages = [d for d in drops if d.pattern == "full_outage"]
    isp_issues = [d for d in drops if d.pattern == "isp_wan_issue"]
    gw_issues = [d for d in drops if d.pattern == "gateway_issue"]
    rf_issues = [d for d in drops if d.pattern == "rf_interference"]

    # --- No drops ---
    if not drops and gw_fails == 0 and wan_fails == 0:
        verdict = "No drops detected during scan"
        confidence = "medium"
        details.append("Connection remained stable throughout monitoring.")
        recs.append(
            "Network was stable during this scan. If drops are intermittent, "
            "run a longer scan: losshound drop-analyze --duration 600"
        )
        return verdict, confidence, details, recs

    # --- Ethernet link flaps ---
    if link_flaps:
        verdict = "ETHERNET LINK FLAPPING"
        confidence = "high" if len(link_flaps) >= 2 else "medium"
        details.append(
            f"The physical Ethernet link went down {len(link_flaps)} time(s). "
            f"This means the connection between your PC and router/switch is "
            f"physically dropping."
        )
        recs.extend([
            "Check your Ethernet cable — try swapping it. A damaged or loose cable "
            "is the #1 cause of link flaps.",
            "Try a different port on your router/switch.",
            "Check your NIC driver — update or roll back the network adapter driver "
            "(Device Manager > Network adapters).",
            "Disable Energy-Efficient Ethernet (EEE/Green Ethernet) in adapter settings — "
            "this power-saving feature causes link drops on some hardware.",
            "If using a USB Ethernet adapter, try a different USB port or a powered hub.",
        ])
        if regularity and "regular" in regularity:
            recs.append(
                f"Drops are happening at {regularity} — this pattern suggests a "
                f"hardware/firmware issue rather than external interference."
            )
        return verdict, confidence, details, recs

    # --- Full outage (gateway + WAN both down) ---
    if full_outages and len(full_outages) >= 2:
        if regularity and "regular" in regularity:
            verdict = "REGULAR FULL OUTAGES — likely modem/router cycling"
            confidence = "high"
            details.append(
                f"Both gateway and WAN drop simultaneously at {regularity}. "
                f"This pattern is classic for a router/modem that is rebooting "
                f"or losing its WAN sync on a cycle."
            )
            recs.extend([
                "Check your router/modem — it may be overheating and rebooting. "
                "Feel if it's hot to the touch.",
                "Check router uptime in its admin panel — if uptime resets at each drop, "
                "the router is rebooting.",
                "Update router firmware.",
                "If you have a separate modem + router, check each independently: "
                "plug directly into the modem to isolate which device is cycling.",
                "Call your ISP — regular sync drops can indicate a line problem or "
                "faulty modem. Ask them to check your line signal levels.",
            ])
        else:
            verdict = "FULL CONNECTIVITY OUTAGES"
            confidence = "high" if len(full_outages) >= 3 else "medium"
            details.append(
                f"Everything drops at once ({len(full_outages)} episodes) — "
                f"gateway, WAN, everything. On Ethernet, this rules out WiFi "
                f"jamming completely."
            )
            recs.extend([
                "This is NOT a WiFi jammer — you're on Ethernet and the drops "
                "affect the entire connection.",
                "Check if your router is rebooting (admin panel > uptime).",
                "Check for modem issues — if you have fiber/DSL/cable, the modem may "
                "be losing sync with the ISP.",
                "Run 'losshound isp-report' and send the results to your ISP as evidence.",
                "Try plugging directly into the modem (bypassing router) to isolate.",
            ])
        return verdict, confidence, details, recs

    # --- ISP/WAN issue (gateway ok, internet drops) ---
    if isp_issues and len(isp_issues) >= 2:
        verdict = "ISP / WAN ISSUE — your local network is fine"
        confidence = "high" if len(isp_issues) >= 3 else "medium"
        details.append(
            f"Gateway stays reachable but WAN/internet drops ({len(isp_issues)} episodes). "
            f"Your local network (Ethernet, router LAN side) is healthy. The problem "
            f"is between your router and the internet."
        )
        recs.extend([
            "This is your ISP or modem's WAN link, not your local network.",
            "Check your modem's WAN/DSL/fiber status lights during a drop.",
            "Run 'losshound isp-report' to generate evidence for your ISP.",
            "Call your ISP — describe the exact pattern: internet drops but LAN stays up.",
            "Ask ISP to check line quality, signal levels, and whether other customers "
            "in your area are affected.",
            "If on DSL: ask about line attenuation and SNR margins.",
            "If on cable: ask about upstream congestion and T3/T4 errors.",
        ])
        return verdict, confidence, details, recs

    # --- Gateway issues (rare — gateway drops but WAN somehow ok) ---
    if gw_issues:
        verdict = "GATEWAY / ROUTER ISSUE"
        confidence = "medium"
        details.append(
            f"Gateway became unreachable while WAN targets responded. "
            f"This can indicate router CPU overload or ARP table issues."
        )
        recs.extend([
            "Restart your router.",
            "Check if router CPU/memory is maxed (admin panel).",
            "Reduce the number of connected devices if possible.",
        ])
        return verdict, confidence, details, recs

    # --- RF interference (WiFi only) ---
    if rf_issues:
        verdict = "POSSIBLE RF INTERFERENCE (WiFi)"
        confidence = "medium"
        details.append(
            f"WiFi signal dropped significantly during outages. "
            f"Could indicate RF interference or a deauth attack."
        )
        recs.extend([
            "Switch to 5GHz band if on 2.4GHz (or vice versa).",
            "Enable 802.11w (PMF) on your router for deauth protection.",
            "Consider switching to Ethernet to rule out WiFi issues.",
        ])
        return verdict, confidence, details, recs

    # --- Some drops but unclear pattern ---
    if drops:
        verdict = "Intermittent connectivity issues"
        confidence = "low"
        details.append(
            f"Detected {len(drops)} drop episodes but the pattern is unclear. "
            f"More data may help."
        )
        recs.extend([
            "Run a longer scan: losshound drop-analyze --duration 600",
            "Run 'losshound isp-report' for comprehensive diagnostics.",
            "Monitor during your typical problem hours.",
        ])
        return verdict, confidence, details, recs

    # Fallback
    verdict = "Minor instability detected"
    confidence = "low"
    recs.append("Run a longer scan to gather more data.")
    return verdict, confidence, details, recs


# ---------------------------------------------------------------------------
# CLI formatting
# ---------------------------------------------------------------------------

def format_drop_report(report: DropAnalysisReport) -> str:
    """Format the drop analysis report for terminal display."""
    lines: list[str] = []
    lines.append("CONNECTIVITY DROP ANALYSIS")
    lines.append("=" * 65)

    # Verdict banner
    lines.append("")
    lines.append(f"  VERDICT: {report.verdict}")
    lines.append(f"  Confidence: {report.confidence}")
    lines.append(f"  Connection: {report.connection_type}")
    lines.append(f"  Scan: {report.scan_duration_seconds:.0f}s "
                 f"({report.total_samples} samples)")
    if report.drop_regularity:
        lines.append(f"  Drop pattern: {report.drop_regularity}")
    lines.append("")

    # Connectivity timeline
    if report.samples:
        lines.append("  CONNECTIVITY TIMELINE")
        chunk_size = max(1, len(report.samples) // 40)
        for i in range(0, len(report.samples), chunk_size):
            chunk = report.samples[i:i + chunk_size]
            ts = chunk[0].timestamp.strftime("%H:%M:%S")
            link_ok = all(s.link_up for s in chunk)
            gw_ok = all(s.gateway_reachable for s in chunk)
            wan_ok = all(s.wan_reachable for s in chunk)

            gw_rtts = [s.gateway_rtt_ms for s in chunk if s.gateway_rtt_ms is not None]
            avg_rtt = f"{sum(gw_rtts)/len(gw_rtts):.0f}ms" if gw_rtts else "--"

            link_s = "UP  " if link_ok else "DOWN"
            gw_s = "OK  " if gw_ok else "LOST"
            wan_s = "OK  " if wan_ok else "LOST"

            bar = _conn_bar(link_ok, gw_ok, wan_ok)
            lines.append(f"    {ts}  {bar}  Link:{link_s} GW:{gw_s} WAN:{wan_s} RTT:{avg_rtt}")

    # Drop events
    if report.drops:
        lines.append("")
        lines.append(f"  DROP EPISODES ({len(report.drops)})")
        lines.append(
            f"  {'Time':<12} {'Duration':<10} {'Link':<7} {'GW':<7} "
            f"{'WAN':<7} {'DNS':<7} {'Classification'}"
        )
        lines.append(
            f"  {'-'*12} {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*22}"
        )
        pattern_labels = {
            "link_flap": "LINK FLAP",
            "full_outage": "FULL OUTAGE",
            "isp_wan_issue": "ISP/WAN",
            "gateway_issue": "GATEWAY",
            "rf_interference": "RF INTERFERENCE",
            "dns_issue": "DNS ONLY",
            "unknown": "UNKNOWN",
        }
        for d in report.drops:
            t = d.start.strftime("%H:%M:%S")
            dur = f"{d.duration_seconds:.0f}s" if d.duration_seconds > 0 else "<3s"
            link = "DOWN" if d.link_lost else "ok"
            gw = "LOST" if d.gateway_lost else "ok"
            wan = "LOST" if d.wan_lost else "ok"
            dns = "FAIL" if d.dns_lost else "ok"
            pat = pattern_labels.get(d.pattern, d.pattern)
            lines.append(
                f"  {t:<12} {dur:<10} {link:<7} {gw:<7} "
                f"{wan:<7} {dns:<7} {pat}"
            )

    # Event log
    if report.events:
        lines.append("")
        lines.append(f"  NETWORK EVENT LOG (last 3 hours, {len(report.events)} events)")
        lines.append(f"  {'Time':<22} {'Source':<10} {'ID':<8} {'Description'}")
        lines.append(f"  {'-'*22} {'-'*10} {'-'*8} {'-'*40}")
        for e in report.events[:25]:
            t = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"  {t:<22} {e.source:<10} {e.event_id:<8} {e.description[:50]}")

    # Details
    if report.details:
        lines.append("")
        lines.append("  ANALYSIS")
        for d in report.details:
            lines.append(f"    - {d}")

    # Recommendations
    if report.recommendations:
        lines.append("")
        lines.append("  RECOMMENDATIONS")
        for i, r in enumerate(report.recommendations, 1):
            lines.append(f"    {i}. {r}")

    lines.append("")
    return "\n".join(lines)


def _conn_bar(link: bool, gw: bool, wan: bool) -> str:
    """Create a compact connectivity bar."""
    if link and gw and wan:
        return "[===]"
    elif link and gw:
        return "[==.]"
    elif link:
        return "[=..]"
    else:
        return "[...]"

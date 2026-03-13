from __future__ import annotations

import signal
import sys
import time
from datetime import datetime

from losshound.core.config import AppConfig
from losshound.core.diagnosis import diagnose
from losshound.core.dns_checks import check_dns
from losshound.core.gateway import detect_gateway
from losshound.core.models import Observation
from losshound.core.ping import ping
from losshound.core.route_monitor import trace_route
from losshound.storage.history import HistoryStore


def run_cli(config: AppConfig):
    """Run Losshound in CLI mode, printing results to stdout."""
    history = HistoryStore()
    running = True

    def handle_signal(sig, frame):
        nonlocal running
        running = False
        print("\nStopping...")

    signal.signal(signal.SIGINT, handle_signal)

    print("Losshound CLI Mode")
    print("=" * 60)
    print(f"Ping targets: {', '.join(config.public_ping_targets)}")
    print(f"DNS targets:  {', '.join(config.dns_test_hostnames)}")
    print(f"Interval:     {config.ping_interval_seconds}s")
    print("=" * 60)
    print()

    cycle = 0
    while running:
        cycle += 1
        now = datetime.now()
        print(f"[{now.strftime('%H:%M:%S')}] Cycle {cycle}")

        # Gateway
        gw = detect_gateway()
        print(f"  Gateway:    {gw or 'not detected'}")

        gw_ping = None
        if gw:
            gw_ping = ping(gw, count=config.ping_count, timeout_ms=config.ping_timeout_ms)
            _print_ping("  GW Ping:", gw_ping)

        # Public pings
        pub_pings = []
        for target in config.public_ping_targets:
            result = ping(target, count=config.ping_count, timeout_ms=config.ping_timeout_ms)
            pub_pings.append(result)
            _print_ping(f"  Ping {target}:", result)

        # DNS
        dns_results = []
        for hostname in config.dns_test_hostnames:
            result = check_dns(hostname)
            dns_results.append(result)
            status = "OK" if result.resolved else "FAIL"
            time_str = f"{result.resolution_time_ms:.0f}ms" if result.resolution_time_ms else "N/A"
            print(f"  DNS {hostname}: {status} ({time_str})")

        # Route (less frequent)
        route_snap = None
        if cycle == 1 or cycle % (config.route_interval_seconds // config.ping_interval_seconds) == 0:
            print("  Running tracert...")
            route_snap = trace_route(config.tracert_target, max_hops=config.tracert_max_hops)
            print(f"  Route: {len(route_snap.hops)} hops ({'complete' if route_snap.completed else 'incomplete'})")

        # Build observation
        obs = Observation(
            timestamp=now,
            gateway_ip=gw,
            gateway_ping=gw_ping,
            public_pings=pub_pings,
            dns_results=dns_results,
            route_snapshot=route_snap,
        )
        history.save_observation(obs)

        # Diagnosis
        recent = history.get_recent_observations(config.diagnosis.window_minutes)
        route_history = history.get_route_snapshots(hours=1)
        diag = diagnose(recent, config.diagnosis, route_history)
        history.save_diagnosis(diag)

        _print_diagnosis(diag)
        print()

        # Wait
        for _ in range(config.ping_interval_seconds):
            if not running:
                break
            time.sleep(1)

    history.close()
    print("Goodbye.")


def _print_ping(label, result):
    if result.timed_out:
        print(f"{label} TIMEOUT (100% loss)")
    else:
        rtt = f"{result.rtt_avg:.0f}ms" if result.rtt_avg is not None else "N/A"
        print(f"{label} {result.loss_percent:.0f}% loss, RTT {rtt}")


def _print_diagnosis(diag):
    markers = {
        "healthy": "+",
        "lan_issue": "!",
        "isp_wan_issue": "!",
        "dns_issue": "?",
        "upstream_route_issue": "~",
        "intermittent": "~",
        "unknown": ".",
    }
    marker = markers.get(diag.category.value, "?")
    print(f"  [{marker}] {diag.summary} (confidence: {diag.confidence})")
    print(f"      {diag.explanation}")

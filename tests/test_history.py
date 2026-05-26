import tempfile
from datetime import datetime
from pathlib import Path

from losshound.core.models import (
    Diagnosis,
    DiagnosisCategory,
    DnsResult,
    Observation,
    PingResult,
    RouteHop,
    RouteSnapshot,
)
from losshound.storage.history import HistoryStore


def _make_store():
    tmp = tempfile.mktemp(suffix=".db")
    return HistoryStore(Path(tmp))


def _make_obs() -> Observation:
    now = datetime.now()
    return Observation(
        timestamp=now,
        gateway_ip="192.168.1.1",
        gateway_ping=PingResult(
            target="192.168.1.1", timestamp=now,
            packets_sent=4, packets_received=4, loss_percent=0.0,
            rtt_avg=5.0,
        ),
        public_pings=[
            PingResult(
                target="1.1.1.1", timestamp=now,
                packets_sent=4, packets_received=4, loss_percent=0.0,
                rtt_avg=12.0,
            ),
        ],
        dns_results=[
            DnsResult(
                hostname="google.com", timestamp=now,
                resolved=True, resolved_ip="142.250.80.46",
                resolution_time_ms=15.0,
            ),
        ],
    )


def test_save_and_load_observation():
    store = _make_store()
    obs = _make_obs()
    store.save_observation(obs)

    loaded = store.get_recent_observations(minutes=5)
    assert len(loaded) == 1
    assert loaded[0].gateway_ip == "192.168.1.1"
    store.close()


def test_save_and_load_diagnosis():
    store = _make_store()
    diag = Diagnosis(
        timestamp=datetime.now(),
        category=DiagnosisCategory.HEALTHY,
        summary="Connection healthy",
        explanation="All good",
        confidence="high",
        evidence={"gateway_loss_avg": 0.0},
    )
    store.save_diagnosis(diag)

    loaded = store.get_recent_diagnoses(10)
    assert len(loaded) == 1
    assert loaded[0]["category"] == "healthy"
    assert loaded[0]["summary"] == "Connection healthy"
    store.close()


def test_save_route_snapshot():
    store = _make_store()
    snap = RouteSnapshot(
        target="8.8.8.8",
        timestamp=datetime.now(),
        hops=[
            RouteHop(1, "192.168.1.1", [1.0, 1.0, 1.0]),
            RouteHop(2, "10.0.0.1", [10.0, 11.0, 10.0]),
        ],
        completed=True,
    )
    store.save_route_snapshot(snap)

    loaded = store.get_route_snapshots(hours=1)
    assert len(loaded) == 1
    assert len(loaded[0].hops) == 2
    assert loaded[0].hops[0].ip == "192.168.1.1"
    store.close()


def test_export_report():
    store = _make_store()
    store.save_observation(_make_obs())
    store.save_diagnosis(Diagnosis(
        timestamp=datetime.now(),
        category=DiagnosisCategory.HEALTHY,
        summary="Healthy",
        explanation="OK",
        confidence="high",
    ))

    report = store.export_report(hours=1)
    assert "generated_at" in report
    assert len(report["observations"]) >= 1
    assert len(report["diagnoses"]) >= 1
    store.close()


def test_prune():
    store = _make_store()
    store.save_observation(_make_obs())
    # Prune with 0 hours retention should remove everything
    removed = store.prune(retention_hours=0)
    assert removed >= 1

    loaded = store.get_recent_observations(minutes=60)
    assert len(loaded) == 0
    store.close()


def test_discovered_devices():
    store = _make_store()
    
    # Save a device
    store.save_device("00-11-22-33-44-55", "192.168.1.50", "Test-Device", "Intel")
    devices = store.get_devices()
    assert len(devices) == 1
    assert devices[0]["mac_address"] == "00-11-22-33-44-55"
    assert devices[0]["status"] == "unknown"
    assert devices[0]["is_active"] is True
    
    # Update device status
    store.update_device_status("00-11-22-33-44-55", "authorized")
    devices = store.get_devices()
    assert devices[0]["status"] == "authorized"
    
    # Set active status to inactive
    store.set_all_devices_inactive()
    devices = store.get_devices()
    assert devices[0]["is_active"] is False
    
    # Update device active status by saving again
    store.save_device("00-11-22-33-44-55", "192.168.1.50", "Test-Device", "Intel")
    devices = store.get_devices()
    assert devices[0]["is_active"] is True
    
    # Clear devices
    store.clear_discovered_devices()
    devices = store.get_devices()
    assert len(devices) == 0
    
    store.close()


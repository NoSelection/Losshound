from datetime import datetime
from pathlib import Path

from losshound.core.alerts import AlertEngine, AlertEvent
from losshound.core.config import AlertsConfig
from losshound.core.models import Diagnosis, DiagnosisCategory
from losshound.storage.history import HistoryStore


def _store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "h.db")


def _diag(category: DiagnosisCategory, ts: datetime) -> Diagnosis:
    return Diagnosis(
        timestamp=ts, category=category,
        summary="test", explanation="",
        confidence="high", evidence={},
    )


def test_healthy_diagnosis_returns_none(tmp_path: Path):
    store = _store(tmp_path)
    try:
        engine = AlertEngine(AlertsConfig(), store)
        result = engine.feed(_diag(DiagnosisCategory.HEALTHY, datetime.now()))
        assert result is None
    finally:
        store.close()


from datetime import timedelta


def test_idle_then_pending_then_alerted(tmp_path: Path):
    store = _store(tmp_path)
    try:
        cfg = AlertsConfig(min_duration_seconds=10)
        engine = AlertEngine(cfg, store)

        t0 = datetime(2026, 5, 11, 18, 0, 0)
        # First unhealthy: IDLE → PENDING, no event
        assert engine.feed(_diag(DiagnosisCategory.LAN_ISSUE, t0)) is None

        # Inside min_duration: still PENDING, no event
        assert engine.feed(
            _diag(DiagnosisCategory.LAN_ISSUE, t0 + timedelta(seconds=5))
        ) is None

        # Past min_duration: ALERTED, event fires
        event = engine.feed(
            _diag(DiagnosisCategory.LAN_ISSUE, t0 + timedelta(seconds=11))
        )
        assert event is not None
        assert event.category == "lan_issue"
        assert event.severity == "warning"
        assert event.is_resolution is False
    finally:
        store.close()


def test_resolution_emitted_when_alerted_then_healthy(tmp_path: Path):
    store = _store(tmp_path)
    try:
        cfg = AlertsConfig(min_duration_seconds=5)
        engine = AlertEngine(cfg, store)

        t0 = datetime(2026, 5, 11, 18, 0, 0)
        engine.feed(_diag(DiagnosisCategory.DNS_ISSUE, t0))
        warning = engine.feed(
            _diag(DiagnosisCategory.DNS_ISSUE, t0 + timedelta(seconds=6))
        )
        assert warning is not None and not warning.is_resolution

        resolution = engine.feed(
            _diag(DiagnosisCategory.HEALTHY, t0 + timedelta(seconds=20))
        )
        assert resolution is not None
        assert resolution.is_resolution is True
        assert resolution.category == "dns_issue"
        assert resolution.severity == "info"
    finally:
        store.close()


def test_pending_then_healthy_emits_no_event(tmp_path: Path):
    store = _store(tmp_path)
    try:
        cfg = AlertsConfig(min_duration_seconds=30)
        engine = AlertEngine(cfg, store)

        t0 = datetime(2026, 5, 11, 18, 0, 0)
        # PENDING but never promoted
        engine.feed(_diag(DiagnosisCategory.LAN_ISSUE, t0))

        result = engine.feed(
            _diag(DiagnosisCategory.HEALTHY, t0 + timedelta(seconds=10))
        )
        assert result is None
    finally:
        store.close()

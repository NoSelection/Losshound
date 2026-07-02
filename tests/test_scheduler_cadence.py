from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QTimer

from losshound.core.config import AppConfig
from losshound.core.models import Diagnosis, DiagnosisCategory, PingResult
from losshound.core.scheduler import (
    FAST_INTERVAL_SECONDS,
    RECOVERY_CYCLES,
    MonitorWorker,
)


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _ping(loss: float = 0.0, timed_out: bool = False) -> PingResult:
    return PingResult(
        target="1.1.1.1",
        timestamp=datetime.now(),
        packets_sent=4,
        packets_received=0 if timed_out else 4,
        loss_percent=loss,
        timed_out=timed_out,
    )


def _worker(qapp) -> MonitorWorker:
    config = AppConfig()
    worker = MonitorWorker(config, MagicMock())
    worker._ping_timer = QTimer()
    worker._ping_timer.setInterval(config.ping_interval_seconds * 1000)
    return worker


def test_loss_densifies_sampling(qapp):
    worker = _worker(qapp)
    emitted: list[int] = []
    worker.cadence_changed.connect(emitted.append)

    worker._update_cadence(_ping(loss=25.0), [_ping()])

    assert worker._fast_mode
    assert worker._ping_timer.interval() == FAST_INTERVAL_SECONDS * 1000
    assert emitted == [FAST_INTERVAL_SECONDS]


def test_public_timeout_densifies_sampling(qapp):
    worker = _worker(qapp)
    worker._update_cadence(_ping(), [_ping(), _ping(timed_out=True, loss=100.0)])
    assert worker._fast_mode


def test_recovery_after_clean_streak(qapp):
    worker = _worker(qapp)
    emitted: list[int] = []
    worker.cadence_changed.connect(emitted.append)

    worker._update_cadence(_ping(loss=50.0), [])
    assert worker._fast_mode

    # One clean cycle is not enough; a relapse resets the streak.
    worker._update_cadence(_ping(), [_ping()])
    worker._update_cadence(_ping(loss=50.0), [])
    assert worker._fast_mode
    for _ in range(RECOVERY_CYCLES - 1):
        worker._update_cadence(_ping(), [_ping()])
    assert worker._fast_mode

    worker._update_cadence(_ping(), [_ping()])
    assert not worker._fast_mode
    assert worker._ping_timer.interval() == worker._config.ping_interval_seconds * 1000
    assert emitted[-1] == worker._config.ping_interval_seconds


def test_healthy_cycles_never_touch_cadence(qapp):
    worker = _worker(qapp)
    emitted: list[int] = []
    worker.cadence_changed.connect(emitted.append)

    for _ in range(5):
        worker._update_cadence(_ping(), [_ping(), _ping()])

    assert not worker._fast_mode
    assert emitted == []


def test_fast_interval_never_exceeds_configured(qapp):
    worker = _worker(qapp)
    worker._config.ping_interval_seconds = 3  # user already faster than fast mode
    worker._update_cadence(_ping(loss=100.0, timed_out=True), [])
    assert worker._ping_timer.interval() == 3 * 1000


# --------------------------------------------------------- Lag spike detection

def _pub(rtt: float) -> PingResult:
    return PingResult(
        target="1.1.1.1",
        timestamp=datetime.now(),
        packets_sent=4,
        packets_received=4,
        loss_percent=0.0,
        rtt_avg=rtt,
    )


def test_baseline_learned_from_healthy_cycles(qapp):
    worker = _worker(qapp)
    worker._maybe_attribute_lag(_ping(), [_pub(20.0), _pub(30.0)])
    assert worker._rtt_baseline == 25.0

    # EMA moves slowly toward new values.
    worker._maybe_attribute_lag(_ping(), [_pub(35.0), _pub(35.0)])
    assert 25.0 < worker._rtt_baseline < 35.0


def test_spike_detected_only_beyond_factor_and_floor(qapp):
    worker = _worker(qapp)
    worker._rtt_baseline = 25.0

    assert not worker._is_rtt_spike(45.0)   # < 2x
    assert not worker._is_rtt_spike(None)
    assert worker._is_rtt_spike(60.0)       # > max(50, 55)

    # High baseline: absolute floor prevents 2x of tiny values triggering.
    worker._rtt_baseline = 10.0
    assert not worker._is_rtt_spike(21.0)   # > 2x but < baseline + 30
    assert worker._is_rtt_spike(41.0)


def test_spike_does_not_pollute_baseline(qapp):
    worker = _worker(qapp)
    worker._rtt_baseline = 25.0
    with_spike = [_pub(200.0)]
    worker._maybe_attribute_lag(_ping(), with_spike)
    assert worker._rtt_baseline == 25.0  # spike cycle skipped by EMA

    # An attribution run was started for the spike.
    assert worker._attr_worker is not None
    worker._attr_worker.requestInterruption()
    worker._attr_worker.wait(5000)


def test_attribution_throttled_by_cooldown(qapp):
    worker = _worker(qapp)
    worker._rtt_baseline = 25.0
    worker._maybe_attribute_lag(_ping(), [_pub(200.0)])
    first_worker = worker._attr_worker
    assert first_worker is not None

    worker._maybe_attribute_lag(_ping(), [_pub(200.0)])
    assert worker._attr_worker is first_worker  # no second launch

    first_worker.requestInterruption()
    first_worker.wait(5000)


# ------------------------------------------------------ Drop forensics trigger

class _FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeDropForensicsThread:
    created = []

    def __init__(self, gateway, wan_target, timeout_streak):
        self.gateway = gateway
        self.wan_target = wan_target
        self.timeout_streak = timeout_streak
        self.forensics_ready = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        self.running = False
        self.created.append(self)

    def isRunning(self):
        return self.running

    def start(self):
        self.started = True
        self.running = True


def _diag_with_streak(streak: int) -> Diagnosis:
    return Diagnosis(
        timestamp=datetime.now(),
        category=DiagnosisCategory.INTERMITTENT,
        summary="Intermittent packet loss detected",
        explanation="test",
        confidence="medium",
        evidence={"max_timeout_streak": streak},
    )


def test_timeout_burst_starts_drop_forensics(qapp, monkeypatch):
    import losshound.core.scheduler as scheduler

    _FakeDropForensicsThread.created = []
    monkeypatch.setattr(scheduler, "DropForensicsThread", _FakeDropForensicsThread)
    worker = _worker(qapp)
    worker._gateway_ip = "192.168.1.1"
    worker._config.public_ping_targets = ["9.9.9.9"]

    worker._maybe_run_drop_forensics(
        _diag_with_streak(worker._config.diagnosis.timeout_burst_threshold)
    )

    assert len(_FakeDropForensicsThread.created) == 1
    created = _FakeDropForensicsThread.created[0]
    assert created.gateway == "192.168.1.1"
    assert created.wan_target == "9.9.9.9"
    assert created.started is True


def test_drop_forensics_ignores_short_timeout_streak(qapp, monkeypatch):
    import losshound.core.scheduler as scheduler

    _FakeDropForensicsThread.created = []
    monkeypatch.setattr(scheduler, "DropForensicsThread", _FakeDropForensicsThread)
    worker = _worker(qapp)
    worker._gateway_ip = "192.168.1.1"

    worker._maybe_run_drop_forensics(
        _diag_with_streak(worker._config.diagnosis.timeout_burst_threshold - 1)
    )

    assert _FakeDropForensicsThread.created == []

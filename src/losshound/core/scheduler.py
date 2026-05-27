from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from losshound.core.config import AppConfig
from losshound.core.diagnosis import diagnose
from losshound.core.dns_checks import check_dns
from losshound.core.gateway import detect_gateway
from losshound.core.models import Diagnosis, DnsResult, Observation, RouteSnapshot
from losshound.core.ping import ping
from losshound.core.route_monitor import trace_route
from losshound.storage.history import HistoryStore

logger = logging.getLogger(__name__)


class MonitorWorker(QObject):
    """Background worker that runs network tests on timers."""

    observation_ready = Signal(object)  # Observation
    diagnosis_ready = Signal(object)    # Diagnosis
    error_occurred = Signal(str)

    def __init__(self, config: AppConfig, history: HistoryStore):
        super().__init__()
        self._config = config
        self._history = history
        self._gateway_ip: Optional[str] = None
        self._last_route: Optional[RouteSnapshot] = None
        self._last_dns_check_monotonic: Optional[float] = None
        self._tracert_running = False
        self._tracert_lock = threading.Lock()
        self._stopped = False

    def start_timers(self):
        """Set up and start the periodic timers."""
        # Ping + DNS timer
        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._run_ping_cycle)
        self._ping_timer.start(self._config.ping_interval_seconds * 1000)

        # Route timer (separate, longer interval)
        self._route_timer = QTimer(self)
        self._route_timer.timeout.connect(self._run_route_check)
        self._route_timer.start(self._config.route_interval_seconds * 1000)

        # Auto mini-benchmark timer. A non-positive interval disables it
        # instead of creating a zero-delay timer that loops continuously.
        self._bench_timer: Optional[QTimer] = None
        self._configure_bench_timer()

        # Prune timer (hourly)
        self._prune_timer = QTimer(self)
        self._prune_timer.timeout.connect(self._prune)
        self._prune_timer.start(3600 * 1000)

        # Run immediately on start
        self._run_ping_cycle()
        self._run_route_check()
        self._prune()

        # Delay auto-benchmark by 2 minutes so startup isn't slow.
        if self._bench_timer and self._bench_timer.isActive():
            QTimer.singleShot(120_000, self._run_auto_benchmark)

    def stop(self):
        self._stopped = True
        if hasattr(self, "_ping_timer"):
            self._ping_timer.stop()
        if hasattr(self, "_route_timer"):
            self._route_timer.stop()
        if getattr(self, "_bench_timer", None):
            self._bench_timer.stop()
        if hasattr(self, "_prune_timer"):
            self._prune_timer.stop()

    def update_config(self, config: AppConfig):
        self._config = config
        if hasattr(self, "_ping_timer"):
            self._ping_timer.setInterval(config.ping_interval_seconds * 1000)
        if hasattr(self, "_route_timer"):
            self._route_timer.setInterval(config.route_interval_seconds * 1000)
        self._configure_bench_timer()

    def _configure_bench_timer(self) -> None:
        interval_minutes = self._config.auto_benchmark_interval_minutes
        timer = getattr(self, "_bench_timer", None)

        if interval_minutes <= 0:
            if timer is not None:
                timer.stop()
            return

        interval_ms = int(interval_minutes * 60 * 1000)
        if timer is None:
            timer = QTimer(self)
            timer.timeout.connect(self._run_auto_benchmark)
            self._bench_timer = timer

        timer.start(interval_ms)

    def _dns_due(self) -> bool:
        interval = max(1, self._config.dns_interval_seconds)
        last_check = self._last_dns_check_monotonic
        return last_check is None or (time.monotonic() - last_check) >= interval

    def _run_ping_cycle(self):
        """Run gateway ping, public pings, and DNS checks."""
        if self._stopped:
            return

        try:
            now = datetime.now()

            # Detect gateway
            self._gateway_ip = detect_gateway()

            # Gateway ping
            gw_ping = None
            if self._gateway_ip:
                gw_ping = ping(
                    self._gateway_ip,
                    count=self._config.ping_count,
                    timeout_ms=self._config.ping_timeout_ms,
                )

            # Public IP pings
            pub_pings = []
            for target in self._config.public_ping_targets:
                if self._stopped or QThread.currentThread().isInterruptionRequested():
                    return
                result = ping(
                    target,
                    count=self._config.ping_count,
                    timeout_ms=self._config.ping_timeout_ms,
                )
                pub_pings.append(result)

            # DNS checks
            dns_results: list[DnsResult] = []
            if self._dns_due():
                for hostname in self._config.dns_test_hostnames:
                    if self._stopped or QThread.currentThread().isInterruptionRequested():
                        return
                    result = check_dns(hostname)
                    dns_results.append(result)
                self._last_dns_check_monotonic = time.monotonic()

            # Build observation
            obs = Observation(
                timestamp=now,
                gateway_ip=self._gateway_ip,
                gateway_ping=gw_ping,
                public_pings=pub_pings,
                dns_results=dns_results,
                route_snapshot=self._last_route,
            )

            self._history.save_observation(obs)
            self.observation_ready.emit(obs)

            # Run diagnosis
            recent = self._history.get_recent_observations(
                self._config.diagnosis.window_minutes
            )
            route_history = self._history.get_route_snapshots(hours=1)

            diag = diagnose(recent, self._config.diagnosis, route_history)
            self._history.save_diagnosis(diag)
            self.diagnosis_ready.emit(diag)

        except (InterruptedError, KeyboardInterrupt):
            logger.info("Ping cycle interrupted during thread shutdown.")
        except Exception as exc:
            if self._stopped or (QThread.currentThread() and QThread.currentThread().isInterruptionRequested()):
                return
            logger.exception("Error in ping cycle")
            self.error_occurred.emit(str(exc))

    def _run_route_check(self):
        """Run a tracert check (skips if one is already running)."""
        if self._stopped:
            return

        with self._tracert_lock:
            if self._tracert_running:
                logger.debug("Tracert already in progress, skipping")
                return
            self._tracert_running = True

        try:
            snap = trace_route(
                self._config.tracert_target,
                max_hops=self._config.tracert_max_hops,
            )
            if self._stopped or QThread.currentThread().isInterruptionRequested():
                return
            self._last_route = snap
            self._history.save_route_snapshot(snap)
        except (InterruptedError, KeyboardInterrupt):
            logger.info("Route check interrupted during thread shutdown.")
        except Exception as exc:
            if self._stopped or (QThread.currentThread() and QThread.currentThread().isInterruptionRequested()):
                return
            logger.exception("Error in route check")
            self.error_occurred.emit(str(exc))
        finally:
            with self._tracert_lock:
                self._tracert_running = False

    def _run_auto_benchmark(self):
        """Run a lightweight auto-benchmark and save to history for trending."""
        if self._stopped:
            return

        try:
            from losshound.core.benchmark import run_benchmark, save_snapshot

            logger.info("Running auto mini-benchmark")
            ping_targets = self._config.public_ping_targets[:1] or ["1.1.1.1"]
            snapshot = run_benchmark(
                label="auto",
                ping_count=max(1, min(self._config.ping_count, 4)),
                ping_targets=ping_targets,
                dns_servers=[],
                tcp_targets=[],
            )
            save_snapshot(snapshot)
            logger.info("Auto mini-benchmark complete — score data saved")
        except Exception as exc:
            logger.debug("Auto benchmark error: %s", exc)

    def _prune(self):
        try:
            self._history.prune(self._config.history_retention_hours)
        except Exception as exc:
            logger.debug("Prune error: %s", exc)


class MonitorThread(QThread):
    """Thread that hosts the MonitorWorker."""

    observation_ready = Signal(object)
    diagnosis_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, config: AppConfig, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._config = config
        self._history = history
        self._worker: Optional[MonitorWorker] = None

    def run(self):
        thread_safe_history = HistoryStore(self._history._db_path)
        try:
            self._worker = MonitorWorker(self._config, thread_safe_history)
            self._worker.observation_ready.connect(self.observation_ready.emit)
            self._worker.diagnosis_ready.connect(self.diagnosis_ready.emit)
            self._worker.error_occurred.connect(self.error_occurred.emit)
            self._worker.start_timers()
            self.exec()
        finally:
            thread_safe_history.close()

    def stop(self):
        if self._worker:
            self._worker.stop()
        self.requestInterruption()
        self.quit()
        # Give the worker a generous window — a tracert in flight can take
        # 30s+. After that, terminate hard; the Job Object will kill any
        # straggler subprocess children when the interpreter exits.
        if not self.wait(3000):
            logger.warning("MonitorThread did not stop cleanly; terminating")
            self.terminate()
            self.wait(1000)

    def update_config(self, config: AppConfig):
        self._config = config
        if self._worker:
            self._worker.update_config(config)

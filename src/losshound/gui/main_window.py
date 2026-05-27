from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QVBoxLayout, QWidget,
)

from losshound.core.config import AppConfig
from losshound.core.models import Diagnosis, Observation
from losshound.core.scheduler import MonitorThread
from losshound.gui.dashboard import DashboardTab
from losshound.gui.drop_tab import DropTab
from losshound.gui.export_tab import ExportTab
from losshound.gui.history_tab import HistoryTab
from losshound.gui.optimizer_tab import OptimizerTab
from losshound.gui.qos_tab import QosTab
from losshound.gui.route_tab import RouteTab
from losshound.gui.score_tab import ScoreTab
from losshound.gui.settings_tab import SettingsTab
from losshound.gui.tray import TrayIcon
from losshound.gui.wifi_tab import WifiTab
from losshound.gui.lan_tab import LANTab
from losshound.gui.branding import app_icon
from losshound.gui.painted import LosshoundTabBar, TexturedSurface
from losshound.gui.theme import get_dark_stylesheet
from losshound.gui.widgets import LosshoundHeader, MonitorStatusBar
from losshound.storage.history import HistoryStore

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._history = HistoryStore()
        self._really_quit = False
        self._paused = False

        self.setWindowTitle("Losshound — Network Diagnosis")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1200, 720)
        self.resize(1480, 880)
        self.setStyleSheet(get_dark_stylesheet())

        # Central widget with tabs (animated halftone backdrop)
        central = TexturedSurface()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top brand rail
        self._header = LosshoundHeader()
        self._header.pause_clicked.connect(self._toggle_pause)
        self._header.run_now_clicked.connect(self._run_now)
        self._header.settings_clicked.connect(self._open_settings)
        layout.addWidget(self._header)

        self._tabs = QTabWidget()
        from losshound.gui.palette import c
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ background: transparent; border: 1px solid {c('border')}; }} "
            f"QTabWidget {{ background: transparent; }} "
            f"QStackedWidget {{ background: transparent; }} "
            f"QWidget#dashboard-tab {{ background: transparent; }}"
        )
        self._tabs.setTabBar(LosshoundTabBar(self._tabs))
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs)

        # Create tabs
        self._dashboard = DashboardTab()
        self._dashboard.setObjectName("dashboard-tab")
        self._history_tab = HistoryTab(self._history)
        self._route_tab = RouteTab(self._history)
        self._settings_tab = SettingsTab(config)
        self._export_tab = ExportTab(self._history)
        self._optimizer_tab = OptimizerTab()
        self._score_tab = ScoreTab()
        self._wifi_tab = WifiTab()
        self._drop_tab = DropTab()
        self._qos_tab = QosTab()
        self._lan_tab = LANTab(self._history)

        self._tabs.addTab(self._dashboard, "Dashboard")
        self._tabs.addTab(self._history_tab, "History")
        self._tabs.addTab(self._route_tab, "Routes")
        self._tabs.addTab(self._optimizer_tab, "Optimizer")
        self._tabs.addTab(self._qos_tab, "QoS")
        self._tabs.addTab(self._score_tab, "Score")
        self._tabs.addTab(self._wifi_tab, "WiFi")
        self._tabs.addTab(self._lan_tab, "LAN Monitor")
        self._tabs.addTab(self._drop_tab, "Drops")
        self._tabs.addTab(self._settings_tab, "Settings")
        self._tabs.addTab(self._export_tab, "Export")

        # Custom monitor status bar
        self._status_bar = MonitorStatusBar()
        layout.addWidget(self._status_bar)
        self._status_bar.set_interval(config.ping_interval_seconds)
        self._status_bar.set_targets(len(getattr(config, "public_ping_targets", [])))
        self._status_bar.set_threads(1)
        self._status_bar.set_monitoring(True)

        # Countdown timer
        self._seconds_until_next = config.ping_interval_seconds
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_timer.start(1000)

        # Alert engine + notification dispatcher + system tray icon
        from losshound.core.alerts import AlertEngine
        from losshound.core.notifications import NotificationDispatcher
        self._alert_engine = AlertEngine(config.alerts, self._history)
        self._notification_dispatcher = NotificationDispatcher(config.alerts)
        self._tray = TrayIcon(self, engine=self._alert_engine)
        self._tray.show_requested.connect(self._show_from_tray)
        self._tray.quit_requested.connect(self._quit_from_tray)
        self._tray.show()

        # Connect settings changes
        self._settings_tab.config_changed.connect(self._on_config_changed)

        # Start the monitor thread
        self._monitor = MonitorThread(config, self._history)
        self._wire_monitor(self._monitor)
        self._monitor.start()

    # ------------------------------------------------------------- Monitoring

    def _wire_monitor(self, monitor: MonitorThread) -> None:
        monitor.observation_ready.connect(self._on_observation)
        monitor.diagnosis_ready.connect(self._on_diagnosis)
        monitor.error_occurred.connect(self._on_error)

    def _on_observation(self, obs: Observation):
        self._dashboard.update_observation(obs)
        self._dashboard.update_route(obs)
        self._route_tab.update_route(obs)
        self._tray.update_observation(obs)
        self._status_bar.set_status_text(
            f"Last check: {obs.timestamp.strftime('%H:%M:%S')}"
        )
        self._seconds_until_next = self._config.ping_interval_seconds

    def _on_diagnosis(self, diag: Diagnosis):
        self._dashboard.update_diagnosis(diag)
        event = self._alert_engine.feed(diag)
        if event is None:
            return
        self._tray.show_event(event)
        self._notification_dispatcher.dispatch(event)

    def _on_error(self, msg: str):
        logger.error("Monitor error: %s", msg)
        self._status_bar.set_status_text(f"Error: {msg[:60]}")

    def _on_config_changed(self, config: AppConfig):
        self._config = config
        self._monitor.update_config(config)
        self._alert_engine.update_config(config.alerts)
        self._notification_dispatcher.update_config(config.alerts)
        self._seconds_until_next = config.ping_interval_seconds
        self._status_bar.set_interval(config.ping_interval_seconds)
        self._status_bar.set_targets(len(getattr(config, "public_ping_targets", [])))

    def _tick_countdown(self):
        if self._paused:
            self._status_bar.set_countdown(0)
            return
        self._seconds_until_next = max(0, self._seconds_until_next - 1)
        self._status_bar.set_countdown(self._seconds_until_next)

    # ----------------------------------------------------------- Header actions

    def _toggle_pause(self) -> None:
        if self._paused:
            # Resume — recreate the monitor thread.
            self._monitor = MonitorThread(self._config, self._history)
            self._wire_monitor(self._monitor)
            self._monitor.start()
            self._paused = False
            self._header.set_paused(False)
            self._status_bar.set_monitoring(True)
            self._status_bar.set_status_text("Monitoring resumed")
        else:
            # Pause — stop the monitor thread.
            try:
                self._monitor.stop()
            except Exception:
                logger.exception("Error stopping monitor for pause")
            self._paused = True
            self._header.set_paused(True)
            self._status_bar.set_monitoring(False)
            self._status_bar.set_status_text("Monitoring paused")

    def _run_now(self) -> None:
        # We don't have a scheduler API for immediate runs; surface a
        # status acknowledgement and rewind the countdown so the next
        # tick fires immediately if we're not paused.
        if self._paused:
            self._status_bar.set_status_text("Resume monitoring first")
            return
        self._seconds_until_next = 1
        self._status_bar.set_status_text("Run-now requested")

    def _open_settings(self) -> None:
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is self._settings_tab:
                self._tabs.setCurrentIndex(i)
                return

    # ------------------------------------------------------------- Tray hooks

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _quit_from_tray(self):
        self._really_quit = True
        self.close()

    # ----------------------------------------------------------- Lifecycle

    def closeEvent(self, event: QCloseEvent):
        close_to_tray = getattr(self._config, "close_to_tray", False)
        if not self._really_quit and close_to_tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(
                "Losshound",
                "Still monitoring in the background. Right-click tray icon to quit.",
                self._tray.MessageIcon.Information,
                2000,
            )
            event.ignore()
            return

        self.shutdown_all()
        event.accept()
        QApplication.instance().quit()

    def shutdown_all(self):
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True

        try:
            self._countdown_timer.stop()
        except Exception:
            pass

        try:
            self._tray.hide()
        except Exception:
            pass

        tab_attrs = (
            "_optimizer_tab", "_wifi_tab", "_qos_tab", "_score_tab",
            "_drop_tab", "_export_tab", "_lan_tab", "_history_tab", "_route_tab",
        )
        for name in tab_attrs:
            tab = getattr(self, name, None)
            if tab is None:
                continue
            shutdown = getattr(tab, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    logger.exception("Error shutting down %s", name)

        try:
            self._monitor.stop()
        except Exception:
            logger.exception("Error stopping monitor thread")

        try:
            self._history.close()
        except Exception:
            logger.exception("Error closing history store")

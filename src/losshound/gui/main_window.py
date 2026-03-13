from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from losshound.core.config import AppConfig
from losshound.core.models import Diagnosis, Observation
from losshound.core.scheduler import MonitorThread
from losshound.gui.dashboard import DashboardTab
from losshound.gui.export_tab import ExportTab
from losshound.gui.history_tab import HistoryTab
from losshound.gui.optimizer_tab import OptimizerTab
from losshound.gui.route_tab import RouteTab
from losshound.gui.score_tab import ScoreTab
from losshound.gui.settings_tab import SettingsTab
from losshound.gui.theme import get_dark_stylesheet
from losshound.storage.history import HistoryStore

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._history = HistoryStore()

        self.setWindowTitle("Losshound — Network Diagnosis")
        self.setMinimumSize(800, 550)
        self.resize(940, 640)
        self.setStyleSheet(get_dark_stylesheet())

        # Central widget with tabs
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Create tabs
        self._dashboard = DashboardTab()
        self._history_tab = HistoryTab(self._history)
        self._route_tab = RouteTab(self._history)
        self._settings_tab = SettingsTab(config)
        self._export_tab = ExportTab(self._history)
        self._optimizer_tab = OptimizerTab()
        self._score_tab = ScoreTab()

        self._tabs.addTab(self._dashboard, "Dashboard")
        self._tabs.addTab(self._history_tab, "History")
        self._tabs.addTab(self._route_tab, "Routes")
        self._tabs.addTab(self._optimizer_tab, "Optimizer")
        self._tabs.addTab(self._score_tab, "Score")
        self._tabs.addTab(self._settings_tab, "Settings")
        self._tabs.addTab(self._export_tab, "Export")

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Starting up...")
        self._status_bar.addWidget(self._status_label)
        self._countdown_label = QLabel("")
        self._status_bar.addPermanentWidget(self._countdown_label)

        # Countdown timer
        self._seconds_until_next = config.ping_interval_seconds
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_timer.start(1000)

        # Connect settings changes
        self._settings_tab.config_changed.connect(self._on_config_changed)

        # Start the monitor thread
        self._monitor = MonitorThread(config, self._history)
        self._monitor.observation_ready.connect(self._on_observation)
        self._monitor.diagnosis_ready.connect(self._on_diagnosis)
        self._monitor.error_occurred.connect(self._on_error)
        self._monitor.start()

    def _on_observation(self, obs: Observation):
        self._dashboard.update_observation(obs)
        self._route_tab.update_route(obs)
        self._status_label.setText(
            f"Last check: {obs.timestamp.strftime('%H:%M:%S')}"
        )
        self._seconds_until_next = self._config.ping_interval_seconds

    def _on_diagnosis(self, diag: Diagnosis):
        self._dashboard.update_diagnosis(diag)

    def _on_error(self, msg: str):
        logger.error("Monitor error: %s", msg)
        self._status_label.setText(f"Error: {msg[:60]}")

    def _on_config_changed(self, config: AppConfig):
        self._config = config
        self._monitor.update_config(config)
        self._seconds_until_next = config.ping_interval_seconds

    def _tick_countdown(self):
        self._seconds_until_next = max(0, self._seconds_until_next - 1)
        self._countdown_label.setText(f"Next check in {self._seconds_until_next}s")

    def closeEvent(self, event):
        self._monitor.stop()
        self._history.close()
        event.accept()

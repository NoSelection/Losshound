from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)

from losshound.core.config import AppConfig, DiagnosisConfig, save_config


class SettingsTab(QWidget):
    config_changed = Signal(object)  # AppConfig

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Targets group
        targets_group = QGroupBox("Targets")
        targets_form = QFormLayout(targets_group)

        self._public_targets = QLineEdit(", ".join(config.public_ping_targets))
        targets_form.addRow("Public ping targets:", self._public_targets)

        self._dns_hostnames = QLineEdit(", ".join(config.dns_test_hostnames))
        targets_form.addRow("DNS test hostnames:", self._dns_hostnames)

        self._tracert_target = QLineEdit(config.tracert_target)
        targets_form.addRow("Tracert target:", self._tracert_target)

        main_layout.addWidget(targets_group)

        # Intervals group
        intervals_group = QGroupBox("Intervals")
        intervals_form = QFormLayout(intervals_group)

        self._ping_interval = QSpinBox()
        self._ping_interval.setRange(5, 600)
        self._ping_interval.setValue(config.ping_interval_seconds)
        self._ping_interval.setSuffix(" sec")
        intervals_form.addRow("Ping interval:", self._ping_interval)

        self._dns_interval = QSpinBox()
        self._dns_interval.setRange(10, 600)
        self._dns_interval.setValue(config.dns_interval_seconds)
        self._dns_interval.setSuffix(" sec")
        intervals_form.addRow("DNS interval:", self._dns_interval)

        self._route_interval = QSpinBox()
        self._route_interval.setRange(60, 3600)
        self._route_interval.setValue(config.route_interval_seconds)
        self._route_interval.setSuffix(" sec")
        intervals_form.addRow("Route interval:", self._route_interval)

        self._ping_count = QSpinBox()
        self._ping_count.setRange(1, 20)
        self._ping_count.setValue(config.ping_count)
        intervals_form.addRow("Pings per check:", self._ping_count)

        self._ping_timeout = QSpinBox()
        self._ping_timeout.setRange(500, 10000)
        self._ping_timeout.setValue(config.ping_timeout_ms)
        self._ping_timeout.setSuffix(" ms")
        intervals_form.addRow("Ping timeout:", self._ping_timeout)

        self._retention = QSpinBox()
        self._retention.setRange(1, 168)
        self._retention.setValue(config.history_retention_hours)
        self._retention.setSuffix(" hours")
        intervals_form.addRow("History retention:", self._retention)

        main_layout.addWidget(intervals_group)

        # Diagnosis thresholds
        diag_group = QGroupBox("Diagnosis Thresholds")
        diag_form = QFormLayout(diag_group)

        dc = config.diagnosis

        self._gw_loss = QDoubleSpinBox()
        self._gw_loss.setRange(1, 100)
        self._gw_loss.setValue(dc.gateway_loss_threshold)
        self._gw_loss.setSuffix(" %")
        diag_form.addRow("Gateway loss threshold:", self._gw_loss)

        self._pub_loss = QDoubleSpinBox()
        self._pub_loss.setRange(1, 100)
        self._pub_loss.setValue(dc.public_loss_threshold)
        self._pub_loss.setSuffix(" %")
        diag_form.addRow("Public loss threshold:", self._pub_loss)

        self._dns_fail = QDoubleSpinBox()
        self._dns_fail.setRange(0.01, 1.0)
        self._dns_fail.setValue(dc.dns_failure_threshold)
        self._dns_fail.setSingleStep(0.05)
        diag_form.addRow("DNS failure threshold:", self._dns_fail)

        self._latency_warn = QDoubleSpinBox()
        self._latency_warn.setRange(10, 5000)
        self._latency_warn.setValue(dc.latency_warning_ms)
        self._latency_warn.setSuffix(" ms")
        diag_form.addRow("Latency warning:", self._latency_warn)

        self._jitter_warn = QDoubleSpinBox()
        self._jitter_warn.setRange(1, 500)
        self._jitter_warn.setValue(dc.jitter_warning_ms)
        self._jitter_warn.setSuffix(" ms")
        diag_form.addRow("Jitter warning:", self._jitter_warn)

        self._route_sensitivity = QSpinBox()
        self._route_sensitivity.setRange(1, 50)
        self._route_sensitivity.setValue(dc.route_change_sensitivity)
        diag_form.addRow("Route change sensitivity:", self._route_sensitivity)

        self._min_obs = QSpinBox()
        self._min_obs.setRange(1, 20)
        self._min_obs.setValue(dc.min_observations)
        diag_form.addRow("Min observations:", self._min_obs)

        self._window = QSpinBox()
        self._window.setRange(1, 60)
        self._window.setValue(dc.window_minutes)
        self._window.setSuffix(" min")
        diag_form.addRow("Diagnosis window:", self._window)

        main_layout.addWidget(diag_group)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)

        save_btn = QPushButton("Save")
        save_btn.setProperty("class", "primary")
        save_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: bold;"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        main_layout.addLayout(btn_row)
        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_config(self) -> AppConfig:
        pub_targets = [
            t.strip() for t in self._public_targets.text().split(",") if t.strip()
        ]
        dns_hosts = [
            t.strip() for t in self._dns_hostnames.text().split(",") if t.strip()
        ]

        diag = DiagnosisConfig(
            gateway_loss_threshold=self._gw_loss.value(),
            public_loss_threshold=self._pub_loss.value(),
            dns_failure_threshold=self._dns_fail.value(),
            latency_warning_ms=self._latency_warn.value(),
            jitter_warning_ms=self._jitter_warn.value(),
            route_change_sensitivity=self._route_sensitivity.value(),
            min_observations=self._min_obs.value(),
            window_minutes=self._window.value(),
        )

        return AppConfig(
            ping_interval_seconds=self._ping_interval.value(),
            dns_interval_seconds=self._dns_interval.value(),
            route_interval_seconds=self._route_interval.value(),
            history_retention_hours=self._retention.value(),
            public_ping_targets=pub_targets,
            dns_test_hostnames=dns_hosts,
            tracert_target=self._tracert_target.text().strip(),
            tracert_max_hops=self._config.tracert_max_hops,
            ping_count=self._ping_count.value(),
            ping_timeout_ms=self._ping_timeout.value(),
            diagnosis=diag,
        )

    def _save(self):
        config = self._build_config()
        save_config(config)
        self._config = config
        self.config_changed.emit(config)
        QMessageBox.information(self, "Settings", "Settings saved successfully.")

    def _reset_defaults(self):
        default = AppConfig()
        self._ping_interval.setValue(default.ping_interval_seconds)
        self._dns_interval.setValue(default.dns_interval_seconds)
        self._route_interval.setValue(default.route_interval_seconds)
        self._ping_count.setValue(default.ping_count)
        self._ping_timeout.setValue(default.ping_timeout_ms)
        self._retention.setValue(default.history_retention_hours)
        self._public_targets.setText(", ".join(default.public_ping_targets))
        self._dns_hostnames.setText(", ".join(default.dns_test_hostnames))
        self._tracert_target.setText(default.tracert_target)

        dc = default.diagnosis
        self._gw_loss.setValue(dc.gateway_loss_threshold)
        self._pub_loss.setValue(dc.public_loss_threshold)
        self._dns_fail.setValue(dc.dns_failure_threshold)
        self._latency_warn.setValue(dc.latency_warning_ms)
        self._jitter_warn.setValue(dc.jitter_warning_ms)
        self._route_sensitivity.setValue(dc.route_change_sensitivity)
        self._min_obs.setValue(dc.min_observations)
        self._window.setValue(dc.window_minutes)

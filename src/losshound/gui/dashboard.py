"""Dashboard tab — 4-column HUD layout backed by BracketedPanel widgets."""
from __future__ import annotations

import platform
import socket
import uuid
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from losshound.core.models import (
    Diagnosis,
    DiagnosisCategory,
    Observation,
)
from losshound.gui.painted import AlertGlyph, BracketedPanel, LiveDot
from losshound.gui.palette import (
    FONT_CHROME_FAMILIES,
    FONT_MONO_FAMILIES,
    c,
    qc,
)
from losshound.gui.theme import button_style
from losshound.gui.widgets import (
    KeyValueRow,
    MetricCard,
    StatusBanner,
)


# ---------------------------------------------------------------------------
# Left-column composite panels
# ---------------------------------------------------------------------------


class StatusPanel(BracketedPanel):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Status", parent=parent)
        self.banner = StatusBanner()
        self.layout().addWidget(self.banner)
        self.layout().addStretch()


class TargetsPanel(BracketedPanel):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Targets", parent=parent)
        self.rows: dict[str, KeyValueRow] = {}
        for key in ("Primary", "Secondary", "Gateway", "DNS"):
            row = KeyValueRow(key, "—", with_dot=True, dot_token="text_dim")
            self.rows[key] = row
            self.layout().addWidget(row)
        self.layout().addStretch()

    def update_from_observation(self, obs: Observation) -> None:
        public = [p for p in obs.public_pings if p.target]
        if public:
            primary = public[0]
            self.rows["Primary"].set_value(primary.target)
            self.rows["Primary"].set_dot(
                "mint" if primary.is_healthy else "error"
            )
        if len(public) > 1:
            secondary = public[1]
            self.rows["Secondary"].set_value(secondary.target)
            self.rows["Secondary"].set_dot(
                "mint" if secondary.is_healthy else "error"
            )

        if obs.gateway_ip:
            self.rows["Gateway"].set_value(obs.gateway_ip)
        if obs.gateway_ping:
            self.rows["Gateway"].set_dot(
                "mint" if obs.gateway_ping.is_healthy else "error"
            )

        if obs.dns_results:
            primary_dns = obs.dns_results[0]
            self.rows["DNS"].set_value(
                primary_dns.resolved_ip or primary_dns.hostname or "—"
            )
            resolved = sum(1 for d in obs.dns_results if d.resolved)
            self.rows["DNS"].set_dot(
                "mint" if resolved == len(obs.dns_results) else "warn"
            )


class SystemPanel(BracketedPanel):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="System", parent=parent)
        self.rows: dict[str, KeyValueRow] = {}
        for key in ("Interface", "Local IP", "MAC", "Uptime", "OS"):
            row = KeyValueRow(key, "—", with_dot=False)
            self.rows[key] = row
            self.layout().addWidget(row)
        self.layout().addStretch()
        self._populate_static()
        self._launched_at = datetime.now()
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_uptime)
        self._tick.start(1000)
        self._refresh_uptime()

    def _populate_static(self) -> None:
        # Local IP best-effort.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("1.1.1.1", 80))
                local_ip = sock.getsockname()[0]
        except OSError:
            local_ip = "—"
        self.rows["Local IP"].set_value(local_ip)

        # MAC
        try:
            mac_int = uuid.getnode()
            mac = ":".join(
                f"{(mac_int >> ele) & 0xff:02X}"
                for ele in range(40, -1, -8)
            )
        except Exception:
            mac = "—"
        self.rows["MAC"].set_value(mac)

        # OS
        try:
            sys_name = platform.system()
            release = platform.release()
            self.rows["OS"].set_value(f"{sys_name} {release}")
        except Exception:
            self.rows["OS"].set_value("—")

        self.rows["Interface"].set_value(
            "Ethernet" if platform.system() == "Windows" else "—"
        )

    def _refresh_uptime(self) -> None:
        delta = datetime.now() - self._launched_at
        seconds = int(delta.total_seconds())
        hours, rem = divmod(seconds, 3600)
        mins, secs = divmod(rem, 60)
        if hours >= 24:
            days, hrs = divmod(hours, 24)
            self.rows["Uptime"].set_value(f"{days}d {hrs}h {mins}m")
        else:
            self.rows["Uptime"].set_value(f"{hours:02d}:{mins:02d}:{secs:02d}")


# ---------------------------------------------------------------------------
# Right-column composite panels
# ---------------------------------------------------------------------------


class AlertsFeed(BracketedPanel):
    """A simple scrolling list of recent diagnoses."""

    MAX_ROWS = 12

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Alerts", parent=parent)
        self.layout().setSpacing(2)
        self._rows: list[QWidget] = []
        self.layout().addStretch()

    def add_alert(self, when: datetime, level: str, text: str) -> None:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)

        time_label = QLabel(when.strftime("%H:%M:%S"))
        time_label.setStyleSheet(
            f"color: {c('info')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        h.addWidget(time_label)

        glyph = AlertGlyph(level)
        h.addWidget(glyph)

        msg = QLabel(text)
        msg.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        h.addWidget(msg, 1)

        # Insert at top, just before the stretch.
        self.layout().insertWidget(0, row)
        self._rows.insert(0, row)
        while len(self._rows) > self.MAX_ROWS:
            old = self._rows.pop()
            old.setParent(None)
            old.deleteLater()


class QosMitigationPanel(BracketedPanel):
    """One-click mitigation offer shown after local-saturation attribution."""

    apply_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Lag mitigation", parent=parent)
        self._app_name = ""

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self.layout().addWidget(self._summary)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self.layout().addWidget(self._status)

        self._apply_button = QPushButton("Apply Bulk QoS")
        self._apply_button.setStyleSheet(button_style("warning"))
        self._apply_button.clicked.connect(self._emit_apply)
        self.layout().addWidget(self._apply_button)

        self.setVisible(False)

    def offer(self, app_name: str, summary: str) -> None:
        self._app_name = app_name
        display_name = self._display_app_name(app_name)
        self._summary.setText(f"{display_name} is the top local-traffic suspect.")
        self._summary.setToolTip(app_name)
        self._apply_button.setToolTip(app_name)
        self._status.setText(summary)
        self._status.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self._apply_button.setText(f"Apply Bulk QoS to {display_name}")
        self._apply_button.setEnabled(True)
        self.setVisible(True)

    def set_pending(self, app_name: str) -> None:
        self._status.setText(f"Applying QoS rule for {app_name}...")
        self._status.setStyleSheet(
            f"color: {c('warn')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self._apply_button.setEnabled(False)

    def set_result(self, success: bool, message: str) -> None:
        token = "mint" if success else "warn"
        self._status.setText(message)
        self._status.setStyleSheet(
            f"color: {c(token)}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self._apply_button.setEnabled(True)

    def _emit_apply(self) -> None:
        if self._app_name:
            self.apply_requested.emit(self._app_name)

    @staticmethod
    def _display_app_name(app_name: str) -> str:
        return app_name if len(app_name) <= 28 else f"{app_name[:25]}..."


class DiagnosisActionsPanel(BracketedPanel):
    """Contextual action buttons driven by diagnosis results."""

    action_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Actions", parent=parent)
        self._buttons: dict[str, QPushButton] = {}

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self.layout().addWidget(self._status)

        self.setVisible(False)

    def set_actions(self, actions: list[dict[str, str]]) -> None:
        self._clear_buttons()
        self._status.setText("")
        if not actions:
            self.setVisible(False)
            return

        for action in actions:
            key = action["key"]
            button = QPushButton(action["label"])
            button.setToolTip(action.get("detail", ""))
            button.setStyleSheet(button_style(action.get("kind", "primary")))
            button.clicked.connect(lambda checked=False, k=key: self.action_requested.emit(k))
            self.layout().addWidget(button)
            self._buttons[key] = button

        self.setVisible(True)

    def set_pending(self, text: str) -> None:
        self._set_buttons_enabled(False)
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {c('warn')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )

    def set_result(self, success: bool, text: str) -> None:
        self._set_buttons_enabled(True)
        token = "mint" if success else "warn"
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {c(token)}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(enabled)

    def _clear_buttons(self) -> None:
        for button in self._buttons.values():
            self.layout().removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._buttons.clear()


class RouteSnapshotPanel(BracketedPanel):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Route snapshot", parent=parent)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Hop", "IP / Host", "Loss %", "Latency"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setShowGrid(True)
        self._table.setFrameShape(QTableWidget.Shape.NoFrame)
        self._table.setStyleSheet(_dashboard_table_qss())
        self._table.verticalHeader().setDefaultSectionSize(24)
        header = self._table.horizontalHeader()
        header.setFixedHeight(30)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 42)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 90)
        self._table.setMinimumHeight(170)
        self.layout().addWidget(self._table)

    def update_route(self, obs: Observation) -> None:
        snap = obs.route_snapshot
        if snap is None:
            return
        self.set_title(f"Route snapshot ({snap.target})")
        self._table.setRowCount(0)
        for hop in snap.hops:
            row = self._table.rowCount()
            self._table.insertRow(row)
            ip = hop.ip or "*"
            samples = [s for s in hop.rtt_samples if s is not None]
            avg = sum(samples) / len(samples) if samples else None
            timed_out = len(samples) == 0
            loss_pct = 100.0 if timed_out else 0.0
            self._table.setItem(row, 0, _cell(str(hop.hop_number)))
            self._table.setItem(row, 1, _cell(ip, color="text_primary"))
            self._table.setItem(row, 2, _cell(f"{loss_pct:.1f}"))
            self._table.setItem(
                row, 3,
                _cell(f"{avg:.2f}" if avg is not None else "—",
                      color="mint" if avg is not None else "text_dim"),
            )


# ---------------------------------------------------------------------------
# Bottom-row tables (LIVE READINGS + RECENT EVENTS)
# ---------------------------------------------------------------------------


class LiveReadingsPanel(BracketedPanel):
    MAX_ROWS = 18

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Live readings", parent=parent)
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Time", "Target", "Type", "RTT (ms)", "Loss %", "Jitter (ms)", "Status"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setShowGrid(True)
        self._table.setFrameShape(QTableWidget.Shape.NoFrame)
        self._table.setStyleSheet(_dashboard_table_qss())
        self._table.verticalHeader().setDefaultSectionSize(24)
        header = self._table.horizontalHeader()
        header.setFixedHeight(30)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(220)
        self.layout().addWidget(self._table)

    def push(self, obs: Observation) -> None:
        rows: list[tuple[str, str, str, Optional[float], Optional[float], Optional[float]]] = []
        time_str = obs.timestamp.strftime("%H:%M:%S")
        for p in obs.public_pings:
            rows.append((time_str, p.target, "ICMP", p.rtt_avg, p.loss_percent, p.rtt_jitter))
        if obs.gateway_ping:
            rows.append((
                time_str,
                obs.gateway_ip or "gateway",
                "ICMP",
                obs.gateway_ping.rtt_avg,
                obs.gateway_ping.loss_percent,
                obs.gateway_ping.rtt_jitter,
            ))
        for d in obs.dns_results:
            rows.append((
                time_str,
                d.resolved_ip or d.hostname,
                "DNS",
                d.resolution_time_ms,
                0.0 if d.resolved else 100.0,
                None,
            ))

        for time_s, target, kind, rtt, loss, jitter in rows:
            row = 0
            self._table.insertRow(row)
            healthy = (loss or 0.0) < 5 and (rtt is not None)
            status_text = "OK" if healthy else "FAIL"
            status_token = "mint" if healthy else "error"
            self._table.setItem(row, 0, _cell(time_s, color="info"))
            self._table.setItem(row, 1, _cell(target, color="text_primary"))
            self._table.setItem(row, 2, _cell(kind))
            self._table.setItem(
                row, 3,
                _cell(f"{rtt:.2f}" if rtt is not None else "—"),
            )
            self._table.setItem(
                row, 4,
                _cell(
                    f"{loss:.2f}" if loss is not None else "—",
                    color="error" if (loss or 0) > 5 else "text_primary",
                ),
            )
            self._table.setItem(
                row, 5,
                _cell(f"{jitter:.2f}" if jitter is not None else "—"),
            )
            self._table.setItem(row, 6, _cell(status_text, color=status_token))

        while self._table.rowCount() > self.MAX_ROWS:
            self._table.removeRow(self._table.rowCount() - 1)


class RecentEventsPanel(BracketedPanel):
    MAX_ROWS = 18

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(title="Recent events", parent=parent)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Time", "Level", "Source", "Event"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setShowGrid(True)
        self._table.setFrameShape(QTableWidget.Shape.NoFrame)
        self._table.setStyleSheet(_dashboard_table_qss())
        self._table.verticalHeader().setDefaultSectionSize(24)
        header = self._table.horizontalHeader()
        header.setFixedHeight(30)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(220)
        self.layout().addWidget(self._table)

    def add(self, when: datetime, level: str, source: str, event: str) -> None:
        row = 0
        self._table.insertRow(row)
        level = level.upper()
        token = {
            "INFO": "info",
            "WARN": "warn",
            "ERROR": "error",
        }.get(level, "text_primary")
        self._table.setItem(row, 0, _cell(when.strftime("%H:%M:%S"), color="info"))
        self._table.setItem(row, 1, _cell(level, color=token))
        self._table.setItem(row, 2, _cell(source, color="text_primary"))
        self._table.setItem(row, 3, _cell(event, color="text_primary"))
        while self._table.rowCount() > self.MAX_ROWS:
            self._table.removeRow(self._table.rowCount() - 1)


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------


def _dashboard_table_qss() -> str:
    return f"""
        QTableWidget {{
            background: transparent;
            alternate-background-color: transparent;
            border: none;
            gridline-color: {c('border_faint')};
            font-family: {FONT_MONO_FAMILIES};
            font-size: 11px;
            color: {c('text_primary')};
        }}
        QTableWidget::item {{
            background: transparent;
            padding: 5px 8px;
            border: none;
        }}
        QHeaderView {{
            background: transparent;
        }}
        QHeaderView::section {{
            background: transparent;
            color: {c('info')};
            border: none;
            border-bottom: 1px solid {c('border')};
            padding: 6px 8px;
            font-family: {FONT_CHROME_FAMILIES};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
        }}
    """


def _cell(text: str, color: str = "text_secondary") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(QColor(c(color)))
    return item


# ---------------------------------------------------------------------------
# DashboardTab
# ---------------------------------------------------------------------------


class DashboardTab(QWidget):
    """The redesigned dashboard."""

    qos_apply_requested = Signal(str)
    diagnosis_action_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        # Scrollable so very small windows still work.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Transparent content widget so the MainWindow's TexturedSurface backdrop shows through.
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        grid = QGridLayout(content)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)

        # ------------------------------------------------------------- Left column
        self.status_panel = StatusPanel()
        self.targets_panel = TargetsPanel()
        self.system_panel = SystemPanel()

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.addWidget(self.status_panel)
        left_col.addWidget(self.targets_panel)
        left_col.addWidget(self.system_panel)
        left_holder = QWidget()
        left_holder.setLayout(left_col)
        left_holder.setStyleSheet("background: transparent;")
        left_holder.setMinimumWidth(300)
        left_holder.setMaximumWidth(320)
        grid.addWidget(left_holder, 0, 0, 3, 1)

        # ------------------------------------------------------------ Centre cards
        self.gateway_card = MetricCard("Gateway", sub_columns=("RTT", "Logs"))
        self.dns_card = MetricCard("DNS", sub_columns=("RTT", "Loss"))
        self.latency_card = MetricCard("Latency", sub_columns=("RTT", "AVG", "MAX"))

        self.public_ip_card = MetricCard("Public IP", sub_columns=("RTT", "Logs"), sparkline=False)
        self.packet_logs_card = MetricCard("Packet logs", sub_columns=("Packet", "Peak"))
        self.jitter_card = MetricCard("Jitter", sub_columns=("KTN", "AVG", "MAX"))

        grid.addWidget(self.gateway_card,    0, 1)
        grid.addWidget(self.dns_card,        1, 1)
        grid.addWidget(self.latency_card,    2, 1)

        grid.addWidget(self.public_ip_card,  0, 2)
        grid.addWidget(self.packet_logs_card, 1, 2)
        grid.addWidget(self.jitter_card,     2, 2)

        # ------------------------------------------------------------ Right column
        self.alerts_panel = AlertsFeed()
        self.qos_mitigation_panel = QosMitigationPanel()
        self.qos_mitigation_panel.apply_requested.connect(
            self.qos_apply_requested.emit
        )
        self.diagnosis_actions_panel = DiagnosisActionsPanel()
        self.diagnosis_actions_panel.action_requested.connect(
            self.diagnosis_action_requested.emit
        )
        self.route_panel = RouteSnapshotPanel()

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.addWidget(self.alerts_panel, 1)
        right_col.addWidget(self.qos_mitigation_panel, 0)
        right_col.addWidget(self.diagnosis_actions_panel, 0)
        right_col.addWidget(self.route_panel, 1)
        right_holder = QWidget()
        right_holder.setLayout(right_col)
        right_holder.setStyleSheet("background: transparent;")
        right_holder.setMinimumWidth(430)
        right_holder.setMaximumWidth(520)
        grid.addWidget(right_holder, 0, 3, 3, 1)

        # ----------------------------------------------------------- Bottom row
        self.readings_panel = LiveReadingsPanel()
        self.events_panel = RecentEventsPanel()

        grid.addWidget(self.readings_panel, 3, 0, 1, 2)
        grid.addWidget(self.events_panel,   3, 2, 1, 2)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 0)
        grid.setRowStretch(0, 0)
        grid.setRowStretch(1, 0)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 1)

    # ----------------------------------------------------------------- API

    def update_observation(self, obs: Observation):
        # Status banner & targets/system reflect the current observation.
        self.targets_panel.update_from_observation(obs)

        # GATEWAY
        if obs.gateway_ping:
            gp = obs.gateway_ping
            self.gateway_card.set_hero(
                obs.gateway_ip or "—",
                status="neutral",
            )
            self.gateway_card.set_sub(
                0,
                f"{gp.rtt_avg:.2f} ms" if gp.rtt_avg is not None else "—",
                status="healthy" if gp.is_healthy else "error",
            )
            self.gateway_card.set_sub(
                1,
                f"{gp.loss_percent:.1f} %",
                status="healthy" if gp.loss_percent < 5 else "error",
            )
            self.gateway_card.push_sample(gp.rtt_avg)
        else:
            self.gateway_card.set_hero("Not detected", status="error")

        # PUBLIC IP — first public ping target IP and stats.
        if obs.public_pings:
            primary = obs.public_pings[0]
            self.public_ip_card.set_hero(primary.target, status="neutral")
            self.public_ip_card.set_sub(
                0,
                f"{primary.rtt_avg:.2f} ms" if primary.rtt_avg is not None else "—",
                status="healthy" if primary.is_healthy else "error",
            )
            self.public_ip_card.set_sub(
                1,
                f"{primary.loss_percent:.1f} %",
                status="healthy" if primary.loss_percent < 5 else "error",
            )

        # DNS card
        if obs.dns_results:
            primary_dns = obs.dns_results[0]
            self.dns_card.set_hero(
                primary_dns.resolved_ip or primary_dns.hostname or "—",
                status="neutral",
            )
            self.dns_card.set_sub(
                0,
                f"{primary_dns.resolution_time_ms:.2f} ms" if primary_dns.resolution_time_ms else "—",
                status="healthy" if primary_dns.resolved else "error",
            )
            resolved = sum(1 for d in obs.dns_results if d.resolved)
            total = len(obs.dns_results)
            self.dns_card.set_sub(
                1,
                f"{(1 - resolved / total) * 100:.1f} %" if total else "—",
                status="healthy" if resolved == total else "warning",
            )
            if primary_dns.resolution_time_ms is not None:
                self.dns_card.push_sample(primary_dns.resolution_time_ms)

        # PACKET LOGS aggregated loss
        all_losses: list[float] = []
        if obs.gateway_ping:
            all_losses.append(obs.gateway_ping.loss_percent)
        all_losses.extend(p.loss_percent for p in obs.public_pings)
        if all_losses:
            mean_loss = sum(all_losses) / len(all_losses)
            peak_loss = max(all_losses)
            self.packet_logs_card.set_hero(
                f"{mean_loss:.2f} %",
                status="healthy" if mean_loss < 2 else ("warning" if mean_loss < 10 else "error"),
            )
            self.packet_logs_card.set_sub(0, f"{mean_loss:.2f} %", status="healthy" if mean_loss < 2 else "warning")
            self.packet_logs_card.set_sub(1, f"{peak_loss:.2f} %", status="healthy" if peak_loss < 5 else "warning")
            self.packet_logs_card.push_sample(mean_loss)

        # LATENCY aggregated
        all_rtts: list[float] = []
        if obs.gateway_ping and obs.gateway_ping.rtt_avg is not None:
            all_rtts.append(obs.gateway_ping.rtt_avg)
        all_rtts.extend(p.rtt_avg for p in obs.public_pings if p.rtt_avg is not None)
        if all_rtts:
            avg = sum(all_rtts) / len(all_rtts)
            mx = max(all_rtts)
            mn = min(all_rtts)
            self.latency_card.set_hero(
                f"{avg:.2f} ms",
                status="healthy" if avg < 50 else ("warning" if avg < 150 else "error"),
            )
            self.latency_card.set_sub(0, f"{mn:.2f}", status="healthy")
            self.latency_card.set_sub(1, f"{avg:.2f}", status="healthy")
            self.latency_card.set_sub(2, f"{mx:.2f}", status="healthy" if mx < 200 else "warning")
            self.latency_card.push_sample(avg)

        # JITTER aggregated
        jitters: list[float] = []
        if obs.gateway_ping and obs.gateway_ping.rtt_jitter is not None:
            jitters.append(obs.gateway_ping.rtt_jitter)
        jitters.extend(p.rtt_jitter for p in obs.public_pings if p.rtt_jitter is not None)
        if jitters:
            avg_j = sum(jitters) / len(jitters)
            mx_j = max(jitters)
            mn_j = min(jitters)
            self.jitter_card.set_hero(
                f"{avg_j:.2f} ms",
                status="healthy" if avg_j < 10 else ("warning" if avg_j < 50 else "error"),
            )
            self.jitter_card.set_sub(0, f"{mn_j:.2f}", status="healthy")
            self.jitter_card.set_sub(1, f"{avg_j:.2f}", status="healthy")
            self.jitter_card.set_sub(2, f"{mx_j:.2f}", status="healthy" if mx_j < 30 else "warning")
            self.jitter_card.push_sample(avg_j)

        # Tables
        self.readings_panel.push(obs)

    def update_diagnosis(self, diag: Diagnosis):
        self.status_panel.banner.update_status(
            diag.summary, diag.explanation, diag.category.value
        )

        # Add to alerts feed + recent events.
        level_for_category = {
            DiagnosisCategory.HEALTHY: "info",
            DiagnosisCategory.LAN_ISSUE: "error",
            DiagnosisCategory.ISP_WAN_ISSUE: "error",
            DiagnosisCategory.DNS_ISSUE: "warn",
            DiagnosisCategory.UPSTREAM_ROUTE_ISSUE: "warn",
            DiagnosisCategory.INTERMITTENT: "warn",
            DiagnosisCategory.UNKNOWN: "info",
        }
        level = level_for_category.get(diag.category, "info")
        self.alerts_panel.add_alert(diag.timestamp, level, diag.summary)
        self.events_panel.add(
            diag.timestamp,
            "INFO" if level == "info" else ("WARN" if level == "warn" else "ERROR"),
            "SYSTEM",
            diag.summary,
        )

    def update_route(self, obs: Observation) -> None:
        self.route_panel.update_route(obs)

    def show_qos_offer(self, app_name: str, summary: str) -> None:
        self.qos_mitigation_panel.offer(app_name, summary)

    def set_qos_offer_pending(self, app_name: str) -> None:
        self.qos_mitigation_panel.set_pending(app_name)

    def set_qos_offer_result(self, success: bool, message: str) -> None:
        self.qos_mitigation_panel.set_result(success, message)

    def set_diagnosis_actions(self, actions: list[dict[str, str]]) -> None:
        self.diagnosis_actions_panel.set_actions(actions)

    def set_diagnosis_action_pending(self, message: str) -> None:
        self.diagnosis_actions_panel.set_pending(message)

    def set_diagnosis_action_result(self, success: bool, message: str) -> None:
        self.diagnosis_actions_panel.set_result(success, message)

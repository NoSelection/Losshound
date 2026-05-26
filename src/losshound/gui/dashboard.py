from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

from losshound.core.models import Diagnosis, DiagnosisCategory, Observation
from losshound.gui.widgets import MetricCard, StatusBanner


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Status banner
        self._banner = StatusBanner()
        layout.addWidget(self._banner)

        # Metrics grid (2x3)
        grid = QGridLayout()
        grid.setSpacing(10)

        self._gw_card = MetricCard("Gateway")
        self._pub_card = MetricCard("Public IP")
        self._dns_card = MetricCard("DNS")
        self._loss_card = MetricCard("Packet Loss")
        self._latency_card = MetricCard("Latency")
        self._jitter_card = MetricCard("Jitter")

        grid.addWidget(self._gw_card, 0, 0)
        grid.addWidget(self._pub_card, 0, 1)
        grid.addWidget(self._dns_card, 0, 2)
        grid.addWidget(self._loss_card, 1, 0)
        grid.addWidget(self._latency_card, 1, 1)
        grid.addWidget(self._jitter_card, 1, 2)

        layout.addLayout(grid)

        # Route status one-liner
        self._route_label = QLabel("Route: waiting for data...")
        self._route_label.setStyleSheet("color: #788596; font-size: 12px; padding: 4px;")
        layout.addWidget(self._route_label)

        # Rolling observation history
        obs_label = QLabel("LIVE READINGS")
        obs_label.setStyleSheet("font-size: 11px; color: #788596; font-weight: bold;")
        layout.addWidget(obs_label)

        self._obs_table = QTableWidget(0, 6)
        self._obs_table.setHorizontalHeaderLabels([
            "Time", "Gateway RTT", "Public RTT", "Loss", "DNS", "Jitter",
        ])
        for col in range(6):
            mode = (
                QHeaderView.ResizeMode.Stretch if col == 0
                else QHeaderView.ResizeMode.ResizeToContents
            )
            self._obs_table.horizontalHeader().setSectionResizeMode(col, mode)
        self._obs_table.verticalHeader().setVisible(False)
        self._obs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._obs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._obs_table.setMaximumHeight(160)
        layout.addWidget(self._obs_table)

        # Recent events table
        events_label = QLabel("RECENT EVENTS")
        events_label.setStyleSheet("font-size: 11px; color: #788596; font-weight: bold;")
        layout.addWidget(events_label)

        self._events_table = QTableWidget(0, 3)
        self._events_table.setHorizontalHeaderLabels(["Time", "Status", "Summary"])
        self._events_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._events_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._events_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._events_table.verticalHeader().setVisible(False)
        self._events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._events_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._events_table.setMaximumHeight(160)
        layout.addWidget(self._events_table)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_observation(self, obs: Observation):
        """Update metric cards from a new observation."""
        # Gateway
        if obs.gateway_ping:
            gp = obs.gateway_ping
            status = "healthy" if gp.is_healthy else "error"
            rtt = f"{gp.rtt_avg:.0f} ms" if gp.rtt_avg is not None else "timeout"
            self._gw_card.set_value(
                obs.gateway_ip or "Unknown",
                f"Loss: {gp.loss_percent:.0f}% | RTT: {rtt}",
                status,
            )
        else:
            self._gw_card.set_value("Not detected", "", "error")

        # Public IP
        if obs.public_pings:
            avg_loss = sum(p.loss_percent for p in obs.public_pings) / len(obs.public_pings)
            rtts = [p.rtt_avg for p in obs.public_pings if p.rtt_avg is not None]
            avg_rtt = sum(rtts) / len(rtts) if rtts else None
            status = "healthy" if avg_loss < 5 else ("warning" if avg_loss < 20 else "error")
            rtt_str = f"{avg_rtt:.0f} ms" if avg_rtt else "N/A"
            self._pub_card.set_value(
                f"{avg_loss:.0f}% loss",
                f"Avg RTT: {rtt_str}",
                status,
            )

        # DNS
        if obs.dns_results:
            resolved = sum(1 for d in obs.dns_results if d.resolved)
            total = len(obs.dns_results)
            times = [d.resolution_time_ms for d in obs.dns_results if d.resolution_time_ms]
            avg_time = sum(times) / len(times) if times else None
            status = "healthy" if resolved == total else ("warning" if resolved > 0 else "error")
            time_str = f"{avg_time:.0f} ms" if avg_time else "N/A"
            self._dns_card.set_value(
                f"{resolved}/{total} OK",
                f"Avg: {time_str}",
                status,
            )

        # Packet loss (overall)
        all_losses = []
        if obs.gateway_ping:
            all_losses.append(obs.gateway_ping.loss_percent)
        all_losses.extend(p.loss_percent for p in obs.public_pings)
        if all_losses:
            overall = sum(all_losses) / len(all_losses)
            status = "healthy" if overall < 2 else ("warning" if overall < 10 else "error")
            self._loss_card.set_value(f"{overall:.1f}%", "", status)

        # Latency
        all_rtts = []
        if obs.gateway_ping and obs.gateway_ping.rtt_avg is not None:
            all_rtts.append(obs.gateway_ping.rtt_avg)
        all_rtts.extend(p.rtt_avg for p in obs.public_pings if p.rtt_avg is not None)
        if all_rtts:
            avg = sum(all_rtts) / len(all_rtts)
            status = "healthy" if avg < 50 else ("warning" if avg < 150 else "error")
            self._latency_card.set_value(f"{avg:.0f} ms", "", status)

        # Jitter
        jitters = []
        if obs.gateway_ping and obs.gateway_ping.rtt_jitter is not None:
            jitters.append(obs.gateway_ping.rtt_jitter)
        jitters.extend(p.rtt_jitter for p in obs.public_pings if p.rtt_jitter is not None)
        if jitters:
            avg_jitter = sum(jitters) / len(jitters)
            status = "healthy" if avg_jitter < 10 else ("warning" if avg_jitter < 50 else "error")
            self._jitter_card.set_value(f"{avg_jitter:.1f} ms", "", status)

        # Rolling observation history row
        self._add_obs_row(obs)

        # Route status
        if obs.route_snapshot:
            rs = obs.route_snapshot
            hop_count = len(rs.hops)
            status_str = "complete" if rs.completed else "incomplete"
            self._route_label.setText(
                f"Route: {hop_count} hops ({status_str}) | "
                f"Last checked: {rs.timestamp.strftime('%H:%M:%S')}"
            )

    def update_diagnosis(self, diag: Diagnosis):
        """Update the status banner and add to events table."""
        self._banner.update_status(
            diag.summary, diag.explanation, diag.category.value
        )

        # Add to events table (prepend)
        row = 0
        self._events_table.insertRow(row)
        self._events_table.setItem(
            row, 0,
            QTableWidgetItem(diag.timestamp.strftime("%H:%M:%S")),
        )

        cat_item = QTableWidgetItem(diag.category.display_name)
        color_map = {
            DiagnosisCategory.HEALTHY: "#75c884",
            DiagnosisCategory.LAN_ISSUE: "#e06363",
            DiagnosisCategory.ISP_WAN_ISSUE: "#e06363",
            DiagnosisCategory.DNS_ISSUE: "#d9b65f",
            DiagnosisCategory.UPSTREAM_ROUTE_ISSUE: "#d9b65f",
            DiagnosisCategory.INTERMITTENT: "#d9b65f",
            DiagnosisCategory.UNKNOWN: "#788596",
        }
        from PySide6.QtGui import QColor
        cat_item.setForeground(QColor(color_map.get(diag.category, "#d8dee9")))
        self._events_table.setItem(row, 1, cat_item)
        self._events_table.setItem(row, 2, QTableWidgetItem(diag.summary))

        # Keep max 50 rows
        while self._events_table.rowCount() > 50:
            self._events_table.removeRow(self._events_table.rowCount() - 1)

    def _add_obs_row(self, obs: Observation):
        """Add a row to the live readings table."""
        from PySide6.QtGui import QColor

        row = 0
        self._obs_table.insertRow(row)

        time_str = obs.timestamp.strftime("%H:%M:%S")

        # Gateway RTT
        gw_rtt = "--"
        if obs.gateway_ping and obs.gateway_ping.rtt_avg is not None:
            gw_rtt = f"{obs.gateway_ping.rtt_avg:.0f} ms"

        # Public RTT (average)
        pub_rtt = "--"
        pub_rtts = [p.rtt_avg for p in obs.public_pings if p.rtt_avg is not None]
        if pub_rtts:
            pub_rtt = f"{sum(pub_rtts) / len(pub_rtts):.0f} ms"

        # Overall loss
        all_losses = []
        if obs.gateway_ping:
            all_losses.append(obs.gateway_ping.loss_percent)
        all_losses.extend(p.loss_percent for p in obs.public_pings)
        loss_str = f"{sum(all_losses) / len(all_losses):.1f}%" if all_losses else "--"

        # DNS
        dns_str = "--"
        if obs.dns_results:
            resolved = sum(1 for d in obs.dns_results if d.resolved)
            dns_str = f"{resolved}/{len(obs.dns_results)}"

        # Jitter
        jitters = []
        if obs.gateway_ping and obs.gateway_ping.rtt_jitter is not None:
            jitters.append(obs.gateway_ping.rtt_jitter)
        jitters.extend(p.rtt_jitter for p in obs.public_pings if p.rtt_jitter is not None)
        jitter_str = f"{sum(jitters) / len(jitters):.1f} ms" if jitters else "--"

        values = [time_str, gw_rtt, pub_rtt, loss_str, dns_str, jitter_str]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # Color loss column red/yellow if elevated
            if col == 3 and all_losses:
                avg_loss = sum(all_losses) / len(all_losses)
                if avg_loss > 10:
                    item.setForeground(QColor("#e06363"))
                elif avg_loss > 2:
                    item.setForeground(QColor("#d9b65f"))
            self._obs_table.setItem(row, col, item)

        # Keep max 30 rows
        while self._obs_table.rowCount() > 30:
            self._obs_table.removeRow(self._obs_table.rowCount() - 1)

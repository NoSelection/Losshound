from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.models import Observation, RouteSnapshot
from losshound.core.route_monitor import diff_routes
from losshound.storage.history import HistoryStore


class RouteTab(QWidget):
    def __init__(self, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._history = history
        self._current_route: RouteSnapshot | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Current route header
        header_label = QLabel("CURRENT ROUTE")
        header_label.setStyleSheet("font-size: 11px; color: #6c7086; font-weight: bold;")
        layout.addWidget(header_label)

        self._route_info = QLabel("Waiting for tracert data...")
        self._route_info.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self._route_info)

        # Route hops table
        self._hops_table = QTableWidget(0, 5)
        self._hops_table.setHorizontalHeaderLabels([
            "Hop", "IP Address", "RTT 1", "RTT 2", "RTT 3",
        ])
        self._hops_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._hops_table.verticalHeader().setVisible(False)
        self._hops_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._hops_table)

        # Route changes section
        changes_label = QLabel("ROUTE CHANGES")
        changes_label.setStyleSheet("font-size: 11px; color: #6c7086; font-weight: bold;")
        layout.addWidget(changes_label)

        self._changes_table = QTableWidget(0, 3)
        self._changes_table.setHorizontalHeaderLabels([
            "Time", "Changed Hops", "Significance",
        ])
        self._changes_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._changes_table.verticalHeader().setVisible(False)
        self._changes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._changes_table.setMaximumHeight(180)
        layout.addWidget(self._changes_table)

        refresh_btn = QPushButton("Refresh History")
        refresh_btn.clicked.connect(self._load_changes)
        layout.addWidget(refresh_btn)

    def update_route(self, obs: Observation):
        if obs.route_snapshot:
            self._current_route = obs.route_snapshot
            self._display_route(obs.route_snapshot)

    def _display_route(self, snap: RouteSnapshot):
        self._route_info.setText(
            f"Target: {snap.target} | "
            f"Hops: {len(snap.hops)} | "
            f"Status: {'Complete' if snap.completed else 'Incomplete'} | "
            f"Time: {snap.timestamp.strftime('%H:%M:%S')}"
        )

        self._hops_table.setRowCount(0)
        for hop in snap.hops:
            row = self._hops_table.rowCount()
            self._hops_table.insertRow(row)

            self._hops_table.setItem(row, 0, QTableWidgetItem(str(hop.hop_number)))
            self._hops_table.setItem(row, 1, QTableWidgetItem(hop.ip or "*"))

            for i, rtt in enumerate(hop.rtt_samples[:3]):
                text = f"{rtt:.0f} ms" if rtt is not None else "*"
                self._hops_table.setItem(row, 2 + i, QTableWidgetItem(text))

    def _load_changes(self):
        self._changes_table.setRowCount(0)
        snapshots = self._history.get_route_snapshots(hours=24)

        if len(snapshots) < 2:
            return

        for i in range(1, len(snapshots)):
            rd = diff_routes(snapshots[i - 1], snapshots[i])
            if not rd.changed_hops:
                continue

            row = self._changes_table.rowCount()
            self._changes_table.insertRow(row)

            self._changes_table.setItem(
                row, 0,
                QTableWidgetItem(rd.new_timestamp.strftime("%Y-%m-%d %H:%M:%S")),
            )
            self._changes_table.setItem(
                row, 1,
                QTableWidgetItem(
                    f"Hops {', '.join(str(h) for h in rd.changed_hops)}"
                ),
            )
            sig = "Significant" if rd.is_significant else "Minor"
            self._changes_table.setItem(row, 2, QTableWidgetItem(sig))

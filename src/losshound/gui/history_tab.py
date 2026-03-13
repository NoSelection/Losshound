from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.storage.history import HistoryStore


class HistoryTab(QWidget):
    def __init__(self, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._history = history

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Controls row
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter:"))

        self._filter = QComboBox()
        self._filter.addItems([
            "All", "Healthy", "LAN Issue", "ISP/WAN Issue",
            "DNS Issue", "Route Issue", "Intermittent",
        ])
        self._filter.currentIndexChanged.connect(self._refresh)
        controls.addWidget(self._filter)

        controls.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        controls.addWidget(refresh_btn)

        layout.addLayout(controls)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            "Time", "Status", "Summary", "Confidence", "Details",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        self._refresh()

    def _refresh(self):
        self._table.setRowCount(0)
        entries = self._history.get_recent_diagnoses(200)

        filter_text = self._filter.currentText()
        filter_map = {
            "Healthy": "healthy",
            "LAN Issue": "lan_issue",
            "ISP/WAN Issue": "isp_wan_issue",
            "DNS Issue": "dns_issue",
            "Route Issue": "upstream_route_issue",
            "Intermittent": "intermittent",
        }

        for entry in entries:
            if filter_text != "All":
                cat = filter_map.get(filter_text)
                if cat and entry["category"] != cat:
                    continue

            row = self._table.rowCount()
            self._table.insertRow(row)

            ts = entry["timestamp"]
            if "T" in ts:
                ts = ts.split("T")[1][:8]

            self._table.setItem(row, 0, QTableWidgetItem(ts))

            cat_item = QTableWidgetItem(entry["category"].replace("_", " ").title())
            color_map = {
                "healthy": "#a6e3a1",
                "lan_issue": "#f38ba8",
                "isp_wan_issue": "#f38ba8",
                "dns_issue": "#f9e2af",
                "upstream_route_issue": "#f9e2af",
                "intermittent": "#f9e2af",
                "unknown": "#6c7086",
            }
            cat_item.setForeground(QColor(color_map.get(entry["category"], "#cdd6f4")))
            self._table.setItem(row, 1, cat_item)

            self._table.setItem(row, 2, QTableWidgetItem(entry["summary"]))
            self._table.setItem(row, 3, QTableWidgetItem(entry["confidence"]))

            # Build detail string from evidence
            ev = entry.get("evidence", {})
            detail_parts = []
            if ev.get("gateway_loss_avg") is not None:
                detail_parts.append(f"GW: {ev['gateway_loss_avg']}%")
            if ev.get("public_loss_avg") is not None:
                detail_parts.append(f"Pub: {ev['public_loss_avg']}%")
            if ev.get("dns_fail_rate") is not None:
                detail_parts.append(f"DNS fail: {ev['dns_fail_rate']:.0%}")
            self._table.setItem(row, 4, QTableWidgetItem(" | ".join(detail_parts)))

        # Scroll to bottom (latest)
        if self._table.rowCount() > 0:
            self._table.scrollToBottom()

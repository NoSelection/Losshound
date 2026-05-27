from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.storage.history import HistoryStore
from losshound.gui.db_workers import DbQueryWorker


class HistoryTab(QWidget):
    def shutdown(self):
        from losshound.gui._shutdown import stop_qthread
        stop_qthread(self._worker)

    def __init__(self, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._history = history
        self._worker: DbQueryWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Controls row
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter:"))

        self._filter = QComboBox()
        self._filter.setFixedWidth(150)
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
            "Date / Time", "Status", "Summary", "Confidence", "Details",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        self._refresh()

    def _refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self._worker = DbQueryWorker(
            self._history._db_path,
            lambda store: store.get_recent_diagnoses(200),
            self,
        )
        self._worker.finished.connect(self._on_refresh_done)
        self._worker.start()

    def _on_refresh_done(self, entries: list[dict]):
        self._table.setRowCount(0)

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
                date_part, time_part = ts.split("T")
                ts = f"{date_part}  {time_part[:8]}"

            ts_item = QTableWidgetItem(ts)
            ts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, ts_item)

            cat_item = QTableWidgetItem(entry["category"].replace("_", " ").title())
            cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color_map = {
                "healthy": "#75c884",
                "lan_issue": "#e06363",
                "isp_wan_issue": "#e06363",
                "dns_issue": "#d9b65f",
                "upstream_route_issue": "#d9b65f",
                "intermittent": "#d9b65f",
                "unknown": "#788596",
            }
            cat_item.setForeground(QColor(color_map.get(entry["category"], "#d8dee9")))
            self._table.setItem(row, 1, cat_item)

            self._table.setItem(row, 2, QTableWidgetItem(entry["summary"]))

            conf_item = QTableWidgetItem(entry["confidence"])
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, conf_item)

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

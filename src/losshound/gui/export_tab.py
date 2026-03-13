from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from losshound.storage.history import HistoryStore


class ExportTab(QWidget):
    def __init__(self, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._history = history

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Report window:"))

        self._hours = QSpinBox()
        self._hours.setRange(1, 24)
        self._hours.setValue(1)
        self._hours.setSuffix(" hours")
        controls.addWidget(self._hours)

        gen_btn = QPushButton("Generate Report")
        gen_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: bold;"
        )
        gen_btn.clicked.connect(self._generate)
        controls.addWidget(gen_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Report preview
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            "Click 'Generate Report' to create a diagnostic report..."
        )
        layout.addWidget(self._preview)

        # Export buttons
        export_row = QHBoxLayout()
        export_row.addStretch()

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        export_row.addWidget(copy_btn)

        txt_btn = QPushButton("Save as TXT")
        txt_btn.clicked.connect(self._save_txt)
        export_row.addWidget(txt_btn)

        json_btn = QPushButton("Save as JSON")
        json_btn.clicked.connect(self._save_json)
        export_row.addWidget(json_btn)

        layout.addLayout(export_row)

        self._report_data: dict | None = None

    def _generate(self):
        hours = self._hours.value()
        self._report_data = self._history.export_report(hours)
        self._preview.setText(self._format_report(self._report_data))

    def _format_report(self, data: dict) -> str:
        lines = [
            "=" * 60,
            "LOSSHOUND DIAGNOSTIC REPORT",
            "=" * 60,
            f"Generated: {data['generated_at']}",
            "",
        ]

        # Latest diagnosis
        if data["diagnoses"]:
            latest = data["diagnoses"][0]
            lines.extend([
                "--- CURRENT DIAGNOSIS ---",
                f"Status:     {latest['summary']}",
                f"Category:   {latest['category']}",
                f"Confidence: {latest['confidence']}",
                f"Detail:     {latest['explanation']}",
                "",
            ])

        # Recent observations summary
        lines.append("--- RECENT OBSERVATIONS ---")
        for obs in data["observations"][:10]:
            gw_loss = f"{obs['gateway_loss']:.0f}%" if obs['gateway_loss'] is not None else "N/A"
            pub_loss = f"{obs['public_loss']:.0f}%" if obs['public_loss'] is not None else "N/A"
            dns_info = f"{obs['dns_failures']}/{obs['dns_total']} failures"
            lines.append(
                f"  {obs['timestamp']}  "
                f"GW: {obs['gateway_ip'] or 'N/A'} ({gw_loss})  "
                f"Public: {pub_loss}  DNS: {dns_info}"
            )

        # Route
        if data["latest_route"]:
            lines.extend(["", "--- LATEST ROUTE ---"])
            for hop in data["latest_route"]:
                ip = hop.get("ip", "*")
                rtt = hop.get("rtt", [])
                rtt_str = "  ".join(
                    f"{r:.0f}ms" if r is not None else "*" for r in rtt[:3]
                )
                lines.append(f"  Hop {hop.get('hop', '?'):>2}  {ip:<16}  {rtt_str}")

        # Diagnosis history
        if len(data["diagnoses"]) > 1:
            lines.extend(["", "--- DIAGNOSIS HISTORY ---"])
            for d in data["diagnoses"][:10]:
                lines.append(
                    f"  {d['timestamp']}  [{d['category']}]  {d['summary']}"
                )

        lines.extend(["", "=" * 60, "End of report", ""])
        return "\n".join(lines)

    def _copy(self):
        text = self._preview.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _save_txt(self):
        text = self._preview.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"losshound_report_{_ts()}.txt",
            "Text Files (*.txt)",
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")

    def _save_json(self):
        if not self._report_data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"losshound_report_{_ts()}.json",
            "JSON Files (*.json)",
        )
        if path:
            Path(path).write_text(
                json.dumps(self._report_data, indent=2), encoding="utf-8"
            )


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

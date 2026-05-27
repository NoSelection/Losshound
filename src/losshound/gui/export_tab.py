from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from losshound.gui.theme import button_style
from losshound.storage.history import HistoryStore


class _IspReportWorker(QObject):
    finished = Signal(str)  # formatted report text

    def __init__(self, history: HistoryStore, hours: int):
        super().__init__()
        self._history = history
        self._hours = hours

    def run(self):
        from losshound.core.isp_report import format_isp_report, generate_isp_report
        report = generate_isp_report(self._history, self._hours)
        text = format_isp_report(report)
        self.finished.emit(text)


class _IspPdfWorker(QObject):
    finished = Signal(object)  # tuple[Path | None, str]  (path, error_msg)

    def __init__(self, history, hours: int, output_path):
        super().__init__()
        self._history = history
        self._hours = hours
        self._output_path = output_path

    def run(self):
        try:
            from losshound.core.isp_report import generate_isp_report
            from losshound.core.isp_report_pdf import render_isp_report_pdf
            report = generate_isp_report(self._history, self._hours)
            render_isp_report_pdf(report, self._output_path)
            self.finished.emit((self._output_path, ""))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("PDF generation failed")
            self.finished.emit((None, str(exc)))


from losshound.gui.db_workers import DbQueryWorker


class ExportTab(QWidget):
    def shutdown(self):
        from losshound.gui._shutdown import stop_qthread
        stop_qthread(getattr(self, "_thread", None))
        stop_qthread(getattr(self, "_quick_worker", None))

    def __init__(self, history: HistoryStore, parent=None):
        super().__init__(parent)
        self._history = history
        self._thread: QThread | None = None
        self._quick_worker: DbQueryWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Report window:"))

        self._hours = QSpinBox()
        self._hours.setRange(1, 168)
        self._hours.setValue(24)
        self._hours.setSuffix(" hours")
        controls.addWidget(self._hours)

        gen_btn = QPushButton("Quick Report")
        gen_btn.setStyleSheet(button_style("primary"))
        gen_btn.clicked.connect(self._generate)
        controls.addWidget(gen_btn)

        isp_btn = QPushButton("ISP Report")
        isp_btn.setStyleSheet(button_style("primary"))
        isp_btn.setToolTip(
            "Generate a comprehensive report with benchmarks, scores, and diagnostics "
            "suitable for sharing with your ISP support team."
        )
        isp_btn.clicked.connect(self._generate_isp)
        controls.addWidget(isp_btn)

        pdf_btn = QPushButton("Save as PDF…")
        pdf_btn.setStyleSheet(button_style("warning"))
        pdf_btn.setToolTip(
            "Generate the ISP report as a polished PDF with charts."
        )
        pdf_btn.clicked.connect(self._generate_pdf)
        controls.addWidget(pdf_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Report preview
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            "Click 'Quick Report' for a basic diagnostic report, or\n"
            "'ISP Report' for a comprehensive report to share with your ISP..."
        )
        self._preview.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
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
        if self._quick_worker is not None and self._quick_worker.isRunning():
            return
        hours = self._hours.value()
        self._preview.setText("Generating quick report...")
        self._quick_worker = DbQueryWorker(
            self._history._db_path,
            lambda store: store.export_report(hours),
            self,
        )
        self._quick_worker.finished.connect(self._on_quick_report_done)
        self._quick_worker.start()

    def _on_quick_report_done(self, data: dict):
        self._report_data = data
        self._preview.setText(self._format_report(data))

    def _generate_isp(self):
        if self._thread is not None and self._thread.isRunning():
            return
        hours = self._hours.value()
        self._preview.setText("Generating ISP report...")

        thread = QThread()
        worker = _IspReportWorker(self._history, hours)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda text: self._on_isp_done(text, thread))
        thread.start()
        self._thread = thread

    def _on_isp_done(self, text: str, thread: QThread):
        thread.quit()
        thread.wait(3000)
        self._preview.setText(text)
        self._report_data = None  # ISP report is text-only for now

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
        if not text:
            QMessageBox.information(
                self, "Nothing to copy",
                "Generate a report first, then copy it to the clipboard.",
            )
            return
        QApplication.clipboard().setText(text)

    def _save_txt(self):
        text = self._preview.toPlainText()
        if not text:
            QMessageBox.information(
                self, "Nothing to save",
                "Generate a report first, then save it as a text file.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"losshound_report_{_ts()}.txt",
            "Text Files (*.txt)",
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")

    def _save_json(self):
        if not self._report_data:
            QMessageBox.information(
                self, "No JSON report",
                "Generate a Quick Report first. ISP reports are text/PDF only.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"losshound_report_{_ts()}.json",
            "JSON Files (*.json)",
        )
        if path:
            Path(path).write_text(
                json.dumps(self._report_data, indent=2), encoding="utf-8"
            )

    def _generate_pdf(self):
        if self._thread is not None and self._thread.isRunning():
            return
        from pathlib import Path
        hours = self._hours.value()
        default_dir = ""
        try:
            from losshound.core.config import load_config
            cfg = load_config()
            if cfg.pdf_default_dir:
                default_dir = cfg.pdf_default_dir
        except Exception:
            pass

        suggested = str(
            Path(default_dir or str(Path.home() / "Documents")) /
            f"Losshound-ISP-Report-{hours}h.pdf"
        )
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save ISP report as PDF", suggested,
            "PDF Files (*.pdf)",
        )
        if not path:
            return

        self._preview.setText(f"Generating PDF report to:\n{path}\n\nPlease wait...")

        thread = QThread()
        worker = _IspPdfWorker(self._history, hours, Path(path))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda res: self._on_pdf_done(res, thread))
        thread.start()
        self._thread = thread

    def _on_pdf_done(self, result, thread: QThread):
        thread.quit()
        thread.wait(3000)
        out_path, error = result
        if out_path is None:
            self._preview.setText(f"PDF generation failed:\n{error}")
            QMessageBox.warning(self, "PDF failed", error)
            return

        self._preview.setText(f"PDF saved to:\n{out_path}")
        try:
            import os
            os.startfile(str(out_path))  # type: ignore[attr-defined]
        except OSError:
            pass


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

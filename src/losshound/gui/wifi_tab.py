"""WiFi Diagnostics tab — channel scan, signal analysis, interference detection."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.wifi_diag import (
    WifiDiagReport, WifiNetwork, run_wifi_diagnostics, format_wifi_report,
)
from losshound.core.load_benchmark import (
    LoadBenchmarkSnapshot, run_load_benchmark, save_load_snapshot,
    format_load_snapshot, get_latest_load_snapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _WifiScanWorker(QThread):
    """Run WiFi diagnostics in background."""

    finished = Signal(object)  # WifiDiagReport
    progress = Signal(str)

    def run(self):
        try:
            self.progress.emit("Scanning WiFi networks...")
            report = run_wifi_diagnostics()
            self.finished.emit(report)
        except Exception as exc:
            logger.error("WiFi scan failed: %s", exc)
            self.finished.emit(None)


class _BufferbloatWorker(QThread):
    """Run bufferbloat test (load benchmark) in background."""

    finished = Signal(object)  # LoadBenchmarkSnapshot
    progress = Signal(str)

    def run(self):
        try:
            snapshot = run_load_benchmark(
                label="bufferbloat-check",
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            save_load_snapshot(snapshot)
            self.finished.emit(snapshot)
        except Exception as exc:
            logger.error("Bufferbloat test failed: %s", exc)
            self.finished.emit(None)


# ---------------------------------------------------------------------------
# WiFi & Bufferbloat Tab
# ---------------------------------------------------------------------------

class WifiTab(QWidget):
    """WiFi diagnostics and bufferbloat detection tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # --- Header ---
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #2a1e3a;
                border: 1px solid #4a2d6a;
                border-radius: 8px;
            }
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("WiFi Diagnostics & Bufferbloat")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #cba6f7; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel(
            "Scan your WiFi environment for interference, check signal quality, "
            "and test for bufferbloat — the #1 cause of lag under load."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #a07ed0; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        main_layout.addWidget(header)

        # --- Action buttons ---
        btn_group = QGroupBox("Actions")
        btn_layout = QHBoxLayout(btn_group)
        btn_layout.setSpacing(8)

        self._wifi_scan_btn = QPushButton("Scan WiFi")
        self._wifi_scan_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 12px 24px;"
        )
        self._wifi_scan_btn.setMinimumHeight(48)
        self._wifi_scan_btn.clicked.connect(self._on_wifi_scan)
        btn_layout.addWidget(self._wifi_scan_btn)

        self._bufferbloat_btn = QPushButton("Test Bufferbloat")
        self._bufferbloat_btn.setStyleSheet(
            "background-color: #f9e2af; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 12px 24px;"
        )
        self._bufferbloat_btn.setMinimumHeight(48)
        self._bufferbloat_btn.setToolTip(
            "Tests if your latency spikes under load (~60s). "
            "This is the most important test for gaming quality."
        )
        self._bufferbloat_btn.clicked.connect(self._on_bufferbloat_test)
        btn_layout.addWidget(self._bufferbloat_btn)

        main_layout.addWidget(btn_group)

        # --- Progress ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Idle")
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                text-align: center;
                color: #cdd6f4;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #cba6f7;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self._progress_bar)

        # --- WiFi status cards ---
        wifi_status_group = QGroupBox("WiFi Connection")
        self._wifi_status_grid = QGridLayout(wifi_status_group)
        self._wifi_status_grid.setSpacing(8)

        self._wifi_cards: dict[str, QLabel] = {}
        card_defs = [
            ("ssid", "SSID"),
            ("signal", "Signal"),
            ("channel", "Channel"),
            ("speed", "Speed"),
            ("radio", "Radio Type"),
            ("band", "Band"),
        ]
        for i, (key, label) in enumerate(card_defs):
            card = self._make_card(label)
            self._wifi_cards[key] = card
            row, col = divmod(i, 3)
            self._wifi_status_grid.addWidget(card, row, col)

        main_layout.addWidget(wifi_status_group)

        # --- Bufferbloat result ---
        bb_group = QGroupBox("Bufferbloat")
        bb_layout = QVBoxLayout(bb_group)

        self._bb_grade_label = QLabel("--")
        self._bb_grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bb_grade_label.setStyleSheet(
            "font-size: 48px; font-weight: bold; color: #585b70; padding: 4px;"
        )
        bb_layout.addWidget(self._bb_grade_label)

        self._bb_detail_label = QLabel(
            "Click 'Test Bufferbloat' to measure how your latency "
            "changes under load (~60 seconds)."
        )
        self._bb_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bb_detail_label.setWordWrap(True)
        self._bb_detail_label.setStyleSheet("color: #a6adc8; padding: 8px; font-size: 13px;")
        bb_layout.addWidget(self._bb_detail_label)

        main_layout.addWidget(bb_group)

        # --- Visible networks table ---
        nets_group = QGroupBox("Visible Networks")
        nets_layout = QVBoxLayout(nets_group)

        self._nets_table = QTableWidget(0, 6)
        self._nets_table.setHorizontalHeaderLabels([
            "SSID", "Signal", "Channel", "Band", "Radio", "Auth",
        ])
        self._nets_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._nets_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._nets_table.setAlternatingRowColors(True)
        self._nets_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        nets_layout.addWidget(self._nets_table)
        main_layout.addWidget(nets_group)

        # --- Channel congestion table ---
        ch_group = QGroupBox("Channel Congestion")
        ch_layout = QVBoxLayout(ch_group)

        self._ch_table = QTableWidget(0, 4)
        self._ch_table.setHorizontalHeaderLabels([
            "Channel", "Band", "Networks", "Avg Signal",
        ])
        self._ch_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._ch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._ch_table.setAlternatingRowColors(True)
        self._ch_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        ch_layout.addWidget(self._ch_table)
        main_layout.addWidget(ch_group)

        # --- Issues & recommendation ---
        advice_group = QGroupBox("Issues & Recommendations")
        advice_layout = QVBoxLayout(advice_group)

        self._advice_label = QLabel("Run a WiFi scan to check for issues.")
        self._advice_label.setWordWrap(True)
        self._advice_label.setStyleSheet("color: #a6adc8; padding: 8px; font-size: 13px;")
        advice_layout.addWidget(self._advice_label)

        main_layout.addWidget(advice_group)

        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Load latest bufferbloat result if available
        self._load_last_bufferbloat()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_card(self, label: str) -> QLabel:
        card = QLabel(f"{label}\n--")
        card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.setStyleSheet("""
            background-color: #2a2a3d;
            border: 1px solid #45475a;
            border-radius: 8px;
            padding: 12px;
            font-size: 12px;
            color: #cdd6f4;
        """)
        card.setMinimumHeight(70)
        card.setWordWrap(True)
        return card

    def _update_card(self, key: str, title: str, value: str, color: str = "#cdd6f4"):
        card = self._wifi_cards.get(key)
        if card:
            card.setText(f"{title}\n{value}")
            card.setStyleSheet(f"""
                background-color: #2a2a3d;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                color: {color};
            """)

    def _set_busy(self, busy: bool, message: str = ""):
        self._wifi_scan_btn.setEnabled(not busy)
        self._bufferbloat_btn.setEnabled(not busy)
        if busy:
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setFormat(message or "Working...")
        else:
            self._progress_bar.setRange(0, 1)
            self._progress_bar.setValue(1)
            self._progress_bar.setFormat(message or "Done")

    def _signal_color(self, pct: int) -> str:
        if pct >= 80:
            return "#a6e3a1"
        if pct >= 60:
            return "#89b4fa"
        if pct >= 40:
            return "#f9e2af"
        if pct >= 20:
            return "#fab387"
        return "#f38ba8"

    def _grade_color(self, grade: str) -> str:
        return {
            "A": "#a6e3a1",
            "B": "#89b4fa",
            "C": "#f9e2af",
            "D": "#fab387",
            "F": "#f38ba8",
        }.get(grade.upper(), "#cdd6f4")

    # ------------------------------------------------------------------
    # WiFi scan
    # ------------------------------------------------------------------

    def _on_wifi_scan(self):
        self._set_busy(True, "Scanning WiFi networks...")
        self._worker = _WifiScanWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_wifi_scan_done)
        self._worker.start()

    def _on_wifi_scan_done(self, report: WifiDiagReport | None):
        self._worker = None
        if report is None:
            self._set_busy(False, "WiFi scan failed")
            QMessageBox.warning(self, "Error", "WiFi scan failed. Check logs.")
            return

        self._set_busy(
            False,
            f"Found {len(report.visible_networks)} networks — "
            f"Signal: {report.signal_quality}",
        )
        self._display_wifi_report(report)

    def _display_wifi_report(self, report: WifiDiagReport):
        """Update all WiFi display widgets."""
        # Status cards
        if report.interface:
            iface = report.interface
            sig_color = self._signal_color(iface.signal_pct)
            self._update_card("ssid", "SSID", iface.ssid or "--")
            self._update_card(
                "signal", "Signal",
                f"{iface.signal_pct}% ({report.signal_quality})",
                sig_color,
            )
            self._update_card("channel", "Channel", f"{iface.channel} ({iface.band})")
            self._update_card("speed", "Speed", f"{iface.speed_mbps:.0f} Mbps")
            self._update_card("radio", "Radio", iface.radio_type or "--")
            self._update_card("band", "Band", iface.band or "--")

        # Networks table
        sorted_nets = sorted(report.visible_networks, key=lambda n: -n.signal_pct)
        self._nets_table.setRowCount(len(sorted_nets))
        for row, net in enumerate(sorted_nets):
            items = [
                QTableWidgetItem(net.ssid),
                QTableWidgetItem(f"{net.signal_pct}%"),
                QTableWidgetItem(str(net.channel)),
                QTableWidgetItem(net.band),
                QTableWidgetItem(net.radio_type),
                QTableWidgetItem(net.auth),
            ]
            sig_color = self._signal_color(net.signal_pct)
            from PySide6.QtGui import QColor
            items[1].setForeground(QColor(sig_color))

            # Highlight current network
            if report.interface and net.ssid == report.interface.ssid:
                for item in items:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

            for col, item in enumerate(items):
                if col >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._nets_table.setItem(row, col, item)

        # Channel congestion
        self._ch_table.setRowCount(len(report.channel_congestion))
        for row, ch in enumerate(report.channel_congestion):
            is_current = (report.interface and ch.channel == report.interface.channel)
            ch_text = f"{ch.channel}" + (" (you)" if is_current else "")
            items = [
                QTableWidgetItem(ch_text),
                QTableWidgetItem(ch.band),
                QTableWidgetItem(str(ch.network_count)),
                QTableWidgetItem(f"{ch.avg_signal:.0f}%"),
            ]
            if is_current:
                for item in items:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor("#cba6f7"))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._ch_table.setItem(row, col, item)

        # Issues & recommendation
        lines = []
        if report.issues:
            for issue in report.issues:
                lines.append(f"\u26a0  {issue}")
            lines.append("")
        lines.append(f"\u2192  {report.recommendation}")

        color = "#a6e3a1" if not report.issues else (
            "#f38ba8" if len(report.issues) >= 3 else "#f9e2af"
        )
        self._advice_label.setText("\n".join(lines))
        self._advice_label.setStyleSheet(
            f"color: {color}; padding: 8px; font-size: 13px;"
        )

    # ------------------------------------------------------------------
    # Bufferbloat
    # ------------------------------------------------------------------

    def _on_bufferbloat_test(self):
        reply = QMessageBox.question(
            self, "Test Bufferbloat",
            "This will download files while measuring your latency\n"
            "to detect bufferbloat. Takes about 60 seconds.\n\n"
            "Your connection will be briefly saturated.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, "Testing bufferbloat (this takes ~60s)...")
        self._worker = _BufferbloatWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_bufferbloat_done)
        self._worker.start()

    def _on_bufferbloat_done(self, snapshot: LoadBenchmarkSnapshot | None):
        self._worker = None
        if snapshot is None:
            self._set_busy(False, "Bufferbloat test failed")
            QMessageBox.warning(self, "Error", "Bufferbloat test failed. Check logs.")
            return

        grade = snapshot.bufferbloat.grade
        self._set_busy(
            False,
            f"Bufferbloat grade: {grade} — "
            f"+{snapshot.bufferbloat.latency_increase_pct:.0f}% latency under load",
        )
        self._display_bufferbloat(snapshot)

    def _display_bufferbloat(self, snapshot: LoadBenchmarkSnapshot):
        bb = snapshot.bufferbloat
        grade = bb.grade
        color = self._grade_color(grade)

        self._bb_grade_label.setText(grade)
        self._bb_grade_label.setStyleSheet(
            f"font-size: 48px; font-weight: bold; color: {color}; padding: 4px;"
        )

        explanations = {
            "A": "Excellent! Latency barely increases under load. Great for gaming.",
            "B": "Good. Slight latency increase but still very usable.",
            "C": "Fair. Noticeable lag spikes when downloading.",
            "D": "Poor. Significant lag when network is busy. Gaming will suffer.",
            "F": "Terrible. Connection becomes nearly unusable under load.",
        }
        explanation = explanations.get(grade, "")

        advice = ""
        if grade in ("C", "D", "F"):
            advice = (
                "\n\nTo fix bufferbloat:\n"
                "  1. Enable SQM/QoS on your router (fq_codel is best)\n"
                "  2. Set bandwidth limits slightly below your max speed\n"
                "  3. Check if your router firmware supports OpenWrt/DD-WRT"
            )

        detail = (
            f"Idle latency: {bb.idle_latency_ms:.1f}ms\n"
            f"Loaded latency: {bb.loaded_latency_ms:.1f}ms\n"
            f"Increase: +{bb.latency_increase_ms:.1f}ms "
            f"(+{bb.latency_increase_pct:.0f}%)\n"
            f"Speed: {snapshot.throughput.speed_mbps:.1f} Mbps\n\n"
            f"{explanation}{advice}"
        )

        self._bb_detail_label.setText(detail)
        self._bb_detail_label.setStyleSheet(
            f"color: {color}; padding: 8px; font-size: 13px;"
        )

    def _load_last_bufferbloat(self):
        """Load the most recent bufferbloat result on startup."""
        try:
            snapshot = get_latest_load_snapshot()
            if snapshot:
                self._display_bufferbloat(snapshot)
        except Exception:
            pass

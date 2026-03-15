"""Drop Analyzer tab — real-time connectivity monitoring to diagnose outages."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.drop_analyzer import (
    DropAnalysisReport, run_drop_analysis, format_drop_report,
)
from losshound.core.gateway import detect_gateway

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _DropAnalyzeWorker(QThread):
    """Run drop analysis in a background thread."""

    finished = Signal(object)   # DropAnalysisReport
    progress = Signal(str)

    def __init__(self, gateway: str, wan_target: str,
                 duration: int, interval: float):
        super().__init__()
        self._gateway = gateway
        self._wan_target = wan_target
        self._duration = duration
        self._interval = interval
        self._stop_requested = False

    def run(self):
        try:
            self.progress.emit("Detecting gateway...")
            gw = self._gateway or detect_gateway()
            if not gw:
                self.progress.emit("Could not detect gateway")
                self.finished.emit(None)
                return

            self.progress.emit(f"Monitoring (GW: {gw})...")
            report = run_drop_analysis(
                gateway=gw,
                wan_target=self._wan_target,
                duration_seconds=self._duration,
                poll_interval=self._interval,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(report)
        except Exception as exc:
            logger.error("Drop analysis failed: %s", exc)
            self.progress.emit(f"Error: {exc}")
            self.finished.emit(None)

    def request_stop(self):
        self._stop_requested = True


# ---------------------------------------------------------------------------
# Drop Analyzer Tab
# ---------------------------------------------------------------------------

class DropTab(QWidget):
    """Connectivity drop analyzer tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _DropAnalyzeWorker | None = None

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
                background-color: #1e2a3a;
                border: 1px solid #2d4a6a;
                border-radius: 8px;
            }
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Connectivity Drop Analyzer")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #89b4fa; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel(
            "Rapidly polls your gateway, WAN, and link state to catch and classify "
            "connectivity drops. Works on both Ethernet and WiFi. Identifies cable "
            "issues, router problems, ISP outages, and more."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #7096c8; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        main_layout.addWidget(header)

        # --- Controls ---
        ctrl_group = QGroupBox("Scan Settings")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(12)

        # Duration
        dur_label = QLabel("Duration:")
        ctrl_layout.addWidget(dur_label)
        self._duration_combo = QComboBox()
        self._duration_combo.addItems([
            "1 minute", "2 minutes", "5 minutes", "10 minutes", "30 minutes", "1 hour",
        ])
        self._duration_combo.setCurrentIndex(1)  # 2 minutes default
        ctrl_layout.addWidget(self._duration_combo)

        # Poll interval
        int_label = QLabel("Poll every:")
        ctrl_layout.addWidget(int_label)
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 30)
        self._interval_spin.setValue(3)
        self._interval_spin.setSuffix("s")
        ctrl_layout.addWidget(self._interval_spin)

        ctrl_layout.addStretch()

        # Start / Stop buttons
        self._start_btn = QPushButton("Start Monitoring")
        self._start_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 12px 28px;"
        )
        self._start_btn.setMinimumHeight(48)
        self._start_btn.clicked.connect(self._on_start)
        ctrl_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 12px 20px;"
        )
        self._stop_btn.setMinimumHeight(48)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        ctrl_layout.addWidget(self._stop_btn)

        main_layout.addWidget(ctrl_group)

        # --- Progress ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Idle — press Start to begin monitoring")
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
                background-color: #89b4fa;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self._progress_bar)

        # --- Verdict banner ---
        self._verdict_frame = QFrame()
        self._verdict_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a3d;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)
        verdict_layout = QVBoxLayout(self._verdict_frame)
        verdict_layout.setContentsMargins(16, 12, 16, 12)

        self._verdict_label = QLabel("--")
        self._verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._verdict_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #585b70; background: transparent;"
        )
        self._verdict_label.setWordWrap(True)
        verdict_layout.addWidget(self._verdict_label)

        self._confidence_label = QLabel("")
        self._confidence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._confidence_label.setStyleSheet(
            "font-size: 12px; color: #6c7086; background: transparent;"
        )
        verdict_layout.addWidget(self._confidence_label)

        main_layout.addWidget(self._verdict_frame)

        # --- Status cards ---
        cards_group = QGroupBox("Connection Status")
        self._cards_grid = QGridLayout(cards_group)
        self._cards_grid.setSpacing(8)

        self._cards: dict[str, QLabel] = {}
        card_defs = [
            ("conn_type", "Connection"),
            ("link", "Link State"),
            ("gateway", "Gateway"),
            ("wan", "WAN / Internet"),
            ("dns", "DNS"),
            ("drops", "Drop Episodes"),
        ]
        for i, (key, label) in enumerate(card_defs):
            card = self._make_card(label)
            self._cards[key] = card
            row, col = divmod(i, 3)
            self._cards_grid.addWidget(card, row, col)

        main_layout.addWidget(cards_group)

        # --- Drop episodes table ---
        drops_group = QGroupBox("Drop Episodes")
        drops_layout = QVBoxLayout(drops_group)

        self._drops_table = QTableWidget(0, 7)
        self._drops_table.setHorizontalHeaderLabels([
            "Time", "Duration", "Link", "Gateway", "WAN", "DNS", "Classification",
        ])
        self._drops_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._drops_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._drops_table.setAlternatingRowColors(True)
        self._drops_table.setStyleSheet("QTableWidget { alternate-background-color: #252538; }")
        drops_layout.addWidget(self._drops_table)

        main_layout.addWidget(drops_group)

        # --- Timeline table ---
        timeline_group = QGroupBox("Connectivity Timeline")
        timeline_layout = QVBoxLayout(timeline_group)

        self._timeline_table = QTableWidget(0, 6)
        self._timeline_table.setHorizontalHeaderLabels([
            "Time", "Link", "Gateway", "GW RTT", "WAN", "WAN RTT",
        ])
        self._timeline_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._timeline_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._timeline_table.setAlternatingRowColors(True)
        self._timeline_table.setStyleSheet("QTableWidget { alternate-background-color: #252538; }")
        self._timeline_table.setMaximumHeight(250)
        timeline_layout.addWidget(self._timeline_table)

        main_layout.addWidget(timeline_group)

        # --- Event log ---
        events_group = QGroupBox("Network Event Log (last 3 hours)")
        events_layout = QVBoxLayout(events_group)

        self._events_table = QTableWidget(0, 4)
        self._events_table.setHorizontalHeaderLabels([
            "Time", "Source", "Event ID", "Description",
        ])
        self._events_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._events_table.setAlternatingRowColors(True)
        self._events_table.setStyleSheet("QTableWidget { alternate-background-color: #252538; }")
        self._events_table.setMaximumHeight(200)
        events_layout.addWidget(self._events_table)

        main_layout.addWidget(events_group)

        # --- Recommendations ---
        recs_group = QGroupBox("Recommendations")
        recs_layout = QVBoxLayout(recs_group)

        self._recs_label = QLabel("Start a scan to analyze your connection.")
        self._recs_label.setWordWrap(True)
        self._recs_label.setStyleSheet("color: #a6adc8; padding: 8px; font-size: 13px;")
        recs_layout.addWidget(self._recs_label)

        main_layout.addWidget(recs_group)

        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

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
        card = self._cards.get(key)
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

    def _duration_seconds(self) -> int:
        mapping = {
            0: 60, 1: 120, 2: 300, 3: 600, 4: 1800, 5: 3600,
        }
        return mapping.get(self._duration_combo.currentIndex(), 120)

    def _set_busy(self, busy: bool, message: str = ""):
        self._start_btn.setEnabled(not busy)
        self._stop_btn.setEnabled(busy)
        self._duration_combo.setEnabled(not busy)
        self._interval_spin.setEnabled(not busy)
        if busy:
            self._progress_bar.setRange(0, 0)  # indeterminate
            self._progress_bar.setFormat(message or "Monitoring...")
        else:
            self._progress_bar.setRange(0, 1)
            self._progress_bar.setValue(1)
            self._progress_bar.setFormat(message or "Done")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def _on_start(self):
        gw = detect_gateway()
        if not gw:
            self._verdict_label.setText("Could not detect gateway")
            self._verdict_label.setStyleSheet(
                "font-size: 20px; font-weight: bold; color: #f38ba8; background: transparent;"
            )
            return

        duration = self._duration_seconds()
        interval = self._interval_spin.value()

        self._set_busy(True, f"Monitoring for {duration}s...")
        self._worker = _DropAnalyzeWorker(
            gateway=gw,
            wan_target="8.8.8.8",
            duration=duration,
            interval=float(interval),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._set_busy(False, "Stopping...")

    def _on_progress(self, msg: str):
        self._progress_bar.setFormat(msg)

    def _on_finished(self, report: DropAnalysisReport | None):
        self._worker = None
        if report is None:
            self._set_busy(False, "Analysis failed")
            self._verdict_label.setText("Analysis failed — check logs")
            return

        drop_count = len(report.drops)
        self._set_busy(
            False,
            f"Done — {report.total_samples} samples, {drop_count} drops detected",
        )
        self._display_report(report)

    # ------------------------------------------------------------------
    # Display results
    # ------------------------------------------------------------------

    def _display_report(self, report: DropAnalysisReport):
        # --- Verdict banner ---
        verdict_colors = {
            "high": ("#f38ba8", "#3a1e2e", "#5a2d45"),
            "medium": ("#f9e2af", "#3a351e", "#5a4d2d"),
            "low": ("#89b4fa", "#1e2a3a", "#2d4a6a"),
        }
        text_color, bg, border = verdict_colors.get(
            report.confidence, ("#cdd6f4", "#2a2a3d", "#45475a")
        )

        # If no drops, use green
        if not report.drops:
            text_color, bg, border = "#a6e3a1", "#1e3a2f", "#2d5a45"

        self._verdict_label.setText(report.verdict)
        self._verdict_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {text_color}; background: transparent;"
        )
        self._confidence_label.setText(
            f"Confidence: {report.confidence}  |  "
            f"Connection: {report.connection_type}  |  "
            f"Duration: {report.scan_duration_seconds:.0f}s"
            + (f"  |  Pattern: {report.drop_regularity}" if report.drop_regularity else "")
        )
        self._verdict_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        # --- Status cards ---
        total = report.total_samples
        gw_fails = sum(1 for s in report.samples if not s.gateway_reachable)
        wan_fails = sum(1 for s in report.samples if not s.wan_reachable)
        link_fails = sum(1 for s in report.samples if not s.link_up)
        dns_fails = sum(1 for s in report.samples if not s.dns_ok)

        self._update_card(
            "conn_type", "Connection",
            report.connection_type.upper(),
            "#89b4fa",
        )
        self._update_card(
            "link", "Link State",
            f"UP ({total - link_fails}/{total})" if link_fails == 0
            else f"FLAPPED ({link_fails} drops)",
            "#a6e3a1" if link_fails == 0 else "#f38ba8",
        )
        self._update_card(
            "gateway", "Gateway",
            f"OK ({total - gw_fails}/{total})" if gw_fails == 0
            else f"FAILED {gw_fails}x",
            "#a6e3a1" if gw_fails == 0 else "#f38ba8",
        )
        self._update_card(
            "wan", "WAN / Internet",
            f"OK ({total - wan_fails}/{total})" if wan_fails == 0
            else f"FAILED {wan_fails}x",
            "#a6e3a1" if wan_fails == 0 else (
                "#f9e2af" if wan_fails < total * 0.1 else "#f38ba8"
            ),
        )
        self._update_card(
            "dns", "DNS",
            f"OK ({total - dns_fails}/{total})" if dns_fails == 0
            else f"FAILED {dns_fails}x",
            "#a6e3a1" if dns_fails == 0 else "#f9e2af",
        )
        self._update_card(
            "drops", "Drop Episodes",
            str(len(report.drops)),
            "#a6e3a1" if len(report.drops) == 0 else (
                "#f9e2af" if len(report.drops) <= 2 else "#f38ba8"
            ),
        )

        # --- Drop episodes table ---
        pattern_labels = {
            "link_flap": "LINK FLAP",
            "full_outage": "FULL OUTAGE",
            "isp_wan_issue": "ISP / WAN",
            "gateway_issue": "GATEWAY",
            "rf_interference": "RF INTERFERENCE",
            "dns_issue": "DNS ONLY",
            "unknown": "UNKNOWN",
        }
        pattern_colors = {
            "link_flap": "#f38ba8",
            "full_outage": "#f38ba8",
            "isp_wan_issue": "#fab387",
            "gateway_issue": "#fab387",
            "rf_interference": "#cba6f7",
            "dns_issue": "#f9e2af",
            "unknown": "#6c7086",
        }

        self._drops_table.setRowCount(len(report.drops))
        for row, drop in enumerate(report.drops):
            t = drop.start.strftime("%H:%M:%S")
            dur = f"{drop.duration_seconds:.0f}s" if drop.duration_seconds > 0 else "<3s"
            link = "DOWN" if drop.link_lost else "ok"
            gw = "LOST" if drop.gateway_lost else "ok"
            wan = "LOST" if drop.wan_lost else "ok"
            dns = "FAIL" if drop.dns_lost else "ok"
            pat = pattern_labels.get(drop.pattern, drop.pattern)
            pat_color = pattern_colors.get(drop.pattern, "#cdd6f4")

            items = [
                QTableWidgetItem(t),
                QTableWidgetItem(dur),
                QTableWidgetItem(link),
                QTableWidgetItem(gw),
                QTableWidgetItem(wan),
                QTableWidgetItem(dns),
                QTableWidgetItem(pat),
            ]

            # Color the problem cells red
            for idx, (val, item) in enumerate(zip(
                [None, None, link, gw, wan, dns, None], items
            )):
                if val in ("DOWN", "LOST", "FAIL"):
                    item.setForeground(QColor("#f38ba8"))
                elif val == "ok":
                    item.setForeground(QColor("#a6e3a1"))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Color the classification
            items[6].setForeground(QColor(pat_color))
            font = items[6].font()
            font.setBold(True)
            items[6].setFont(font)

            for col, item in enumerate(items):
                self._drops_table.setItem(row, col, item)

        # --- Timeline table (show samples, chunked) ---
        samples = report.samples
        chunk_size = max(1, len(samples) // 40)
        chunks = [samples[i:i + chunk_size] for i in range(0, len(samples), chunk_size)]

        self._timeline_table.setRowCount(len(chunks))
        for row, chunk in enumerate(chunks):
            ts = chunk[0].timestamp.strftime("%H:%M:%S")
            link_ok = all(s.link_up for s in chunk)
            gw_ok = all(s.gateway_reachable for s in chunk)
            wan_ok = all(s.wan_reachable for s in chunk)

            gw_rtts = [s.gateway_rtt_ms for s in chunk if s.gateway_rtt_ms is not None]
            wan_rtts = [s.wan_rtt_ms for s in chunk if s.wan_rtt_ms is not None]
            gw_rtt_str = f"{sum(gw_rtts)/len(gw_rtts):.0f}ms" if gw_rtts else "--"
            wan_rtt_str = f"{sum(wan_rtts)/len(wan_rtts):.0f}ms" if wan_rtts else "--"

            items = [
                QTableWidgetItem(ts),
                QTableWidgetItem("UP" if link_ok else "DOWN"),
                QTableWidgetItem("OK" if gw_ok else "LOST"),
                QTableWidgetItem(gw_rtt_str),
                QTableWidgetItem("OK" if wan_ok else "LOST"),
                QTableWidgetItem(wan_rtt_str),
            ]

            # Colors
            items[1].setForeground(QColor("#a6e3a1" if link_ok else "#f38ba8"))
            items[2].setForeground(QColor("#a6e3a1" if gw_ok else "#f38ba8"))
            items[4].setForeground(QColor("#a6e3a1" if wan_ok else "#f38ba8"))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._timeline_table.setItem(row, col, item)

        # --- Event log ---
        events = report.events[:25]
        self._events_table.setRowCount(len(events))
        for row, evt in enumerate(events):
            items = [
                QTableWidgetItem(evt.timestamp.strftime("%Y-%m-%d %H:%M:%S")),
                QTableWidgetItem(evt.source),
                QTableWidgetItem(str(evt.event_id)),
                QTableWidgetItem(evt.description[:60]),
            ]
            for col, item in enumerate(items):
                if col >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._events_table.setItem(row, col, item)

        # --- Recommendations ---
        if report.recommendations:
            recs_text = "\n".join(
                f"{i}. {r}" for i, r in enumerate(report.recommendations, 1)
            )
            rec_color = "#f38ba8" if report.drops else "#a6e3a1"
            self._recs_label.setText(recs_text)
            self._recs_label.setStyleSheet(
                f"color: {rec_color}; padding: 8px; font-size: 13px;"
            )
        else:
            self._recs_label.setText("No issues found.")
            self._recs_label.setStyleSheet(
                "color: #a6e3a1; padding: 8px; font-size: 13px;"
            )

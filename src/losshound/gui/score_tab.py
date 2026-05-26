"""Score & Trends tab — network quality scoring with historical analysis."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.benchmark import BenchmarkSnapshot, run_benchmark, save_snapshot
from losshound.core.scoring import NetworkScore, SubScore, format_score, score_snapshot
from losshound.core.trending import TrendSummary, analyze_trends, format_trends
from losshound.gui.theme import button_style
from losshound.gui.widgets import TelemetryHeader
from losshound.storage.history import HistoryStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ScoreWorker(QThread):
    """Run a benchmark and compute network score."""

    finished = Signal(object, object)  # (BenchmarkSnapshot, NetworkScore)
    progress = Signal(str)

    def run(self):
        try:
            self.progress.emit("Running benchmark for score...")
            snapshot = run_benchmark(
                label="score", ping_count=20,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            save_snapshot(snapshot)
            score = score_snapshot(snapshot)
            self.finished.emit(snapshot, score)
        except Exception as exc:
            logger.error("Score benchmark failed: %s", exc)
            self.finished.emit(None, None)


class _TrendsWorker(QThread):
    """Load history and run trend analysis."""

    finished = Signal(object, list)  # (TrendSummary, list[dict])

    def __init__(self, hours: int = 168):
        super().__init__()
        self._hours = hours

    def run(self):
        try:
            store = HistoryStore()
            benchmarks = store.get_benchmarks(hours=self._hours)
            store.close()
            summary = analyze_trends(benchmarks, hours=self._hours)
            self.finished.emit(summary, benchmarks)
        except Exception as exc:
            logger.error("Trend analysis failed: %s", exc)
            self.finished.emit(None, [])


# ---------------------------------------------------------------------------
# Score & Trends Tab
# ---------------------------------------------------------------------------

class ScoreTab(QWidget):
    """Network quality score and historical trends tab."""

    def shutdown(self):
        from losshound.gui._shutdown import stop_qthread
        stop_qthread(getattr(self, "_worker", None))

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        main_layout.addWidget(TelemetryHeader(
            "Network Score & Trends",
            "Score network quality for gaming and real-time use, then track degradation over time.",
            "SCORE",
            "HISTORY",
            "#62c7d8",
        ))

        # --- Action buttons ---
        btn_group = QGroupBox("Actions")
        btn_layout = QHBoxLayout(btn_group)
        btn_layout.setSpacing(8)

        self._score_btn = QPushButton("Run Score Benchmark")
        self._score_btn.setStyleSheet(button_style("primary"))
        self._score_btn.setMinimumHeight(42)
        self._score_btn.clicked.connect(self._on_run_score)
        btn_layout.addWidget(self._score_btn)

        self._trends_btn = QPushButton("Refresh Trends")
        self._trends_btn.setStyleSheet(button_style("default"))
        self._trends_btn.setMinimumHeight(42)
        self._trends_btn.clicked.connect(self._on_refresh_trends)
        btn_layout.addWidget(self._trends_btn)

        main_layout.addWidget(btn_group)

        # --- Progress ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Idle")
        main_layout.addWidget(self._progress_bar)

        # --- Score display ---
        score_group = QGroupBox("Network Score")
        score_layout = QHBoxLayout(score_group)
        score_layout.setContentsMargins(12, 16, 12, 12)
        score_layout.setSpacing(16)

        # Left: Main Score Card
        from PySide6.QtWidgets import QFrame
        self._main_score_card = QFrame()
        self._main_score_card.setFrameShape(QFrame.Shape.StyledPanel)
        self._main_score_card.setFixedWidth(240)
        self._main_score_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141822, stop:1 #0d1016);
                border: 1px solid #20293a;
                border-radius: 0px;
            }
            QFrame:hover {
                border-color: #62c7d8;
            }
        """)

        main_card_layout = QVBoxLayout(self._main_score_card)
        main_card_layout.setContentsMargins(16, 20, 16, 20)
        main_card_layout.setSpacing(12)
        main_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel("OVERALL SCORE")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: #788596;
            text-transform: uppercase;
            letter-spacing: 1.5px;
        """)
        main_card_layout.addWidget(title_label)

        # Big score number
        self._score_label = QLabel("--")
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_label.setStyleSheet(
            "font-size: 72px; font-weight: 900; color: #4a5565; padding: 0px; font-family: 'Segoe UI Variable', sans-serif;"
        )
        main_card_layout.addWidget(self._score_label)

        self._grade_label = QLabel("Run benchmark to score")
        self._grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #8f9aaa; padding: 4px;")
        self._grade_label.setWordWrap(True)
        main_card_layout.addWidget(self._grade_label)

        score_layout.addWidget(self._main_score_card)

        # Right: Sub-score cards grid
        self._subscore_grid = QGridLayout()
        self._subscore_grid.setSpacing(8)
        self._subscore_cards: dict[str, QLabel] = {}
        score_layout.addLayout(self._subscore_grid)

        main_layout.addWidget(score_group)

        # --- History table ---
        history_group = QGroupBox("Benchmark History")
        history_layout = QVBoxLayout(history_group)

        self._history_table = QTableWidget(0, 7)
        self._history_table.setHorizontalHeaderLabels([
            "Timestamp", "Label", "Score", "Grade", "Latency", "Jitter", "Loss",
        ])
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #141923; }
        """)
        history_layout.addWidget(self._history_table)
        main_layout.addWidget(history_group)

        # --- Patterns / alerts ---
        patterns_group = QGroupBox("Detected Patterns")
        patterns_layout = QVBoxLayout(patterns_group)

        self._patterns_label = QLabel("Run a few benchmarks over time to detect patterns.")
        self._patterns_label.setWordWrap(True)
        self._patterns_label.setStyleSheet("color: #8f9aaa; padding: 8px; font-size: 13px;")
        patterns_layout.addWidget(self._patterns_label)

        main_layout.addWidget(patterns_group)

        # --- Metric trend table ---
        metric_group = QGroupBox("Metric Trends")
        metric_layout = QVBoxLayout(metric_group)

        self._metric_table = QTableWidget(0, 6)
        self._metric_table.setHorizontalHeaderLabels([
            "Metric", "Current", "Average", "Best", "Worst", "Trend",
        ])
        self._metric_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._metric_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._metric_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._metric_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._metric_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._metric_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._metric_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._metric_table.verticalHeader().setVisible(False)
        self._metric_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._metric_table.setAlternatingRowColors(True)
        self._metric_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #141923; }
        """)
        metric_layout.addWidget(self._metric_table)
        main_layout.addWidget(metric_group)

        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Load trends on startup
        self._on_refresh_trends()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, message: str = ""):
        self._score_btn.setEnabled(not busy)
        self._trends_btn.setEnabled(not busy)
        if busy:
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setFormat(message or "Working...")
        else:
            self._progress_bar.setRange(0, 1)
            self._progress_bar.setValue(1)
            self._progress_bar.setFormat(message or "Done")

    def _score_color(self, score: float) -> str:
        """Return a hex color for a score value."""
        if score >= 90:
            return "#75c884"  # green
        if score >= 75:
            return "#62c7d8"  # blue
        if score >= 60:
            return "#d9b65f"  # yellow
        if score >= 40:
            return "#c98652"  # orange
        return "#e06363"      # red

    # ------------------------------------------------------------------
    # Score actions
    # ------------------------------------------------------------------

    def _on_run_score(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        self._set_busy(True, "Running score benchmark...")
        self._worker = _ScoreWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_score_done)
        self._worker.start()

    def _on_score_done(self, snapshot, score: NetworkScore | None):
        self._worker = None
        if score is None:
            self._set_busy(False, "Score benchmark failed")
            QMessageBox.warning(self, "Error", "Score benchmark failed. Check logs.")
            return

        self._set_busy(False, f"Score: {score.overall:.0f}/100 ({score.grade})")
        self._display_score(score)
        self._on_refresh_trends()

    def _display_score(self, score: NetworkScore):
        """Update the score display widgets."""
        color = self._score_color(score.overall)

        self._score_label.setText(f"{score.overall:.0f}")
        self._score_label.setStyleSheet(
            f"font-size: 72px; font-weight: 900; color: {color}; padding: 0px; font-family: 'Segoe UI Variable', sans-serif;"
        )

        self._grade_label.setText(
            f"GRADE {score.grade} • {score.rating.upper()}"
        )
        self._grade_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color}; padding: 6px 12px; "
            f"background-color: {color}1a; border: 1px solid {color}4d; border-radius: 0px;"
        )

        self._main_score_card.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141822, stop:1 #0d1016);
                border: 1px solid {color}33;
                border-radius: 0px;
            }}
            QFrame:hover {{
                border-color: #62c7d8;
            }}
        """)

        # Clear old sub-score cards
        for card in self._subscore_cards.values():
            self._subscore_grid.removeWidget(card)
            card.deleteLater()
        self._subscore_cards.clear()

        # Create new sub-score cards
        for i, sub in enumerate(score.sub_scores):
            raw_str = f"{sub.raw_value:.1f}{sub.raw_unit}" if sub.raw_unit != "grade" else f"Grade {sub.raw_value:.0f}"
            if sub.name == "Packet Loss":
                raw_str = f"{sub.raw_value:.1f}%"
            elif sub.name == "Bufferbloat":
                raw_str = f"+{sub.raw_value:.0f}%" if sub.raw_value > 0 else "None"

            card = QLabel(
                f"<div style='line-height: 1.2;'>"
                f"<span style='font-size: 10px; font-weight: bold; color: #788596; text-transform: uppercase;'>{sub.name}</span><br/>"
                f"<span style='font-size: 22px; font-weight: 900; color: {self._score_color(sub.value)};'>{sub.value:.0f}</span>"
                f"<span style='font-size: 11px; color: #52637a;'>/100</span><br/>"
                f"<span style='font-size: 11px; font-family: monospace; color: #a9b7c6;'>{raw_str} ({sub.rating})</span>"
                f"</div>"
            )
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_color = self._score_color(sub.value)
            card.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141822, stop:1 #0d1016);
                    border: 1px solid {sub_color}2b;
                    border-radius: 0px;
                    padding: 10px;
                }}
                QLabel:hover {{
                    border-color: #62c7d8;
                }}
            """)
            card.setMinimumHeight(80)
            card.setWordWrap(True)
            row, col = divmod(i, 3)
            self._subscore_grid.addWidget(card, row, col)
            self._subscore_cards[sub.name] = card

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def _on_refresh_trends(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        self._worker = _TrendsWorker(hours=168)
        self._worker.finished.connect(self._on_trends_done)
        self._worker.start()

    def _on_trends_done(self, summary: TrendSummary | None, benchmarks: list[dict]):
        self._worker = None
        if summary is None:
            return

        self._populate_history_table(benchmarks)
        self._populate_metric_table(summary)
        self._populate_patterns(summary)

        # Load the latest full snapshot to compute sub-scores and display the full score dashboard
        from losshound.core.benchmark import get_latest_snapshot
        from losshound.core.scoring import score_snapshot
        
        latest_snap = get_latest_snapshot()
        if latest_snap:
            try:
                score = score_snapshot(latest_snap)
                self._display_score(score)
            except Exception as exc:
                logger.warning("Failed to score latest snapshot on trends done: %s", exc)
        elif summary.current_score is not None:
            color = self._score_color(summary.current_score)
            self._score_label.setText(f"{summary.current_score:.0f}")
            self._score_label.setStyleSheet(
                f"font-size: 72px; font-weight: 900; color: {color}; padding: 0px; font-family: 'Segoe UI Variable', sans-serif;"
            )
            grade = "A" if summary.current_score >= 90 else (
                "B" if summary.current_score >= 75 else (
                    "C" if summary.current_score >= 60 else (
                        "D" if summary.current_score >= 40 else "F"
                    )
                )
            )
            self._grade_label.setText(f"Grade {grade} — Last benchmark score")
            self._grade_label.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {color}; padding: 4px;"
            )

    def _populate_history_table(self, benchmarks: list[dict]):
        """Fill the history table with benchmark entries."""
        # Show most recent 30
        entries = benchmarks[-30:]
        entries.reverse()  # newest first

        self._history_table.setRowCount(len(entries))
        for row, b in enumerate(entries):
            ts = b.get("timestamp", "--")[:19].replace('T', ' ')
            label = b.get("label", "--") or "--"
            score_val = b.get("overall_score")
            grade = b.get("grade") or "--"
            lat = f"{b['avg_latency_ms']:.1f}ms" if b.get("avg_latency_ms") is not None else "--"
            jit = f"{b['avg_jitter_ms']:.1f}ms" if b.get("avg_jitter_ms") is not None else "--"
            loss = f"{b['avg_loss_pct']:.1f}%" if b.get("avg_loss_pct") is not None else "--"

            items = [
                QTableWidgetItem(ts),
                QTableWidgetItem(label),
                QTableWidgetItem(f"{score_val:.0f}" if score_val is not None else "--"),
                QTableWidgetItem(grade),
                QTableWidgetItem(lat),
                QTableWidgetItem(jit),
                QTableWidgetItem(loss),
            ]

            # Color the score
            if score_val is not None:
                color = self._score_color(score_val)
                from PySide6.QtGui import QColor
                items[2].setForeground(QColor(color))
                items[3].setForeground(QColor(color))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._history_table.setItem(row, col, item)

    def _populate_metric_table(self, summary: TrendSummary):
        """Fill the metric trend table."""
        metrics = list(summary.metric_summaries.values())
        self._metric_table.setRowCount(len(metrics))

        _TREND_COLORS = {
            "improving": Qt.GlobalColor.green,
            "degrading": Qt.GlobalColor.red,
            "stable": Qt.GlobalColor.white,
        }

        for row, mt in enumerate(metrics):
            cur = f"{mt.current:.1f}" if mt.current is not None else "--"
            items = [
                QTableWidgetItem(mt.metric.capitalize()),
                QTableWidgetItem(cur),
                QTableWidgetItem(f"{mt.average:.1f}"),
                QTableWidgetItem(f"{mt.best:.1f}"),
                QTableWidgetItem(f"{mt.worst:.1f}"),
                QTableWidgetItem(mt.trend_direction.capitalize()),
            ]

            color = _TREND_COLORS.get(mt.trend_direction, Qt.GlobalColor.white)
            items[5].setForeground(color)

            for col, item in enumerate(items):
                if col >= 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._metric_table.setItem(row, col, item)

    def _populate_patterns(self, summary: TrendSummary):
        """Display detected patterns."""
        if not summary.patterns:
            if summary.snapshot_count >= 5:
                self._patterns_label.setText(
                    "<div style='padding: 12px; background: #0f131a; border: 1px solid #1f2735; "
                    "color: #75c884; font-weight: bold; border-radius: 0px; font-size: 12px;'>"
                    "<span style='color: #75c884;'>●</span> &nbsp; NO CONCERNING PATTERNS DETECTED &nbsp; "
                    "| &nbsp; <span style='color: #a9b7c6; font-weight: normal;'>Your network is stable.</span>"
                    "</div>"
                )
            else:
                count_needed = 5 - summary.snapshot_count
                self._patterns_label.setText(
                    f"<div style='padding: 12px; background: #0f131a; border: 1px solid #1f2735; "
                    f"color: #788596; border-radius: 0px; font-size: 12px; font-weight: bold;'>"
                    f"<span style='color: #788596;'>ℹ</span> &nbsp; INSUFFICIENT DATA &nbsp; "
                    f"| &nbsp; <span style='color: #a9b7c6; font-weight: normal;'>"
                    f"Need {count_needed} more benchmark(s) to detect patterns. "
                    f"Run 'Run Score Benchmark' a few more times.</span>"
                    f"</div>"
                )
            self._patterns_label.setStyleSheet("padding: 4px; font-size: 13px; background: transparent;")
            return

        _COLORS = {
            "degradation": "#e06363",
            "time_of_day": "#d9b65f",
            "improving": "#75c884",
            "volatile": "#c98652",
            "weekday_vs_weekend": "#a78bfa",
        }

        html_lines = []
        for p in summary.patterns:
            color = _COLORS.get(p.pattern_type, "#d8dee9")

            type_titles = {
                "degradation": "Degradation Detected",
                "time_of_day": "Time-Of-Day Variation",
                "improving": "Health Improvement",
                "volatile": "Latency Volatility",
                "weekday_vs_weekend": "Weekday vs Weekend Difference",
                "stable": "Performance Stability",
            }
            title = type_titles.get(p.pattern_type, "Network Pattern").upper()

            conf_pct = p.confidence * 100.0
            conf_str = f"Confidence: {conf_pct:.0f}%"

            metric_tag = p.metric.upper()
            if metric_tag == "DNS":
                metric_tag = "DNS RESOLUTION"
            elif metric_tag == "TCP":
                metric_tag = "TCP CONNECT"
            elif metric_tag == "LOSS":
                metric_tag = "PACKET LOSS"
            elif metric_tag == "SCORE":
                metric_tag = "OVERALL SCORE"

            html_lines.append(
                f"<div style='margin-bottom: 8px; padding: 12px; background: #0f131a; border: 1px solid #1f2735; border-radius: 0px;'>"
                f"<table width='100%' cellpadding='0' cellspacing='0' border='0'>"
                f"  <tr>"
                f"    <td style='font-size: 11px; font-weight: bold; letter-spacing: 0.5px;'>"
                f"      <span style='color: {color}; font-size: 12px;'>●</span> &nbsp; "
                f"      <span style='color: #e6edf6; text-transform: uppercase;'>{title}</span> &nbsp; "
                f"      <span style='color: #788596; font-size: 9px; font-weight: bold;'>| &nbsp; {metric_tag}</span>"
                f"    </td>"
                f"    <td align='right' style='color: #788596; font-size: 10px; font-family: monospace; font-weight: bold;'>"
                f"      {conf_str}"
                f"    </td>"
                f"  </tr>"
                f"  <tr>"
                f"    <td colspan='2' style='padding-top: 6px; font-size: 12px; color: #a9b7c6; font-family: sans-serif; line-height: 1.4;'>"
                f"      {p.description}"
                f"    </td>"
                f"  </tr>"
                f"</table>"
                f"</div>"
            )

        self._patterns_label.setText("".join(html_lines))
        self._patterns_label.setStyleSheet("padding: 4px; font-size: 13px; background: transparent;")

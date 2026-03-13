"""Score & Trends tab — network quality scoring with historical analysis."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.benchmark import BenchmarkSnapshot, run_benchmark, save_snapshot
from losshound.core.scoring import NetworkScore, SubScore, format_score, score_snapshot
from losshound.core.trending import TrendSummary, analyze_trends, format_trends
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
                background-color: #1e2a3a;
                border: 1px solid #2d4a6a;
                border-radius: 8px;
            }
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Network Score & Trends")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #89b4fa; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel(
            "Score your network 0–100 for gaming and real-time use. "
            "Track performance over time and detect degradation patterns."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #7ea9d0; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)

        main_layout.addWidget(header)

        # --- Action buttons ---
        btn_group = QGroupBox("Actions")
        btn_layout = QHBoxLayout(btn_group)
        btn_layout.setSpacing(8)

        self._score_btn = QPushButton("Run Score Benchmark")
        self._score_btn.setStyleSheet(
            "background-color: #89b4fa; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 12px 24px;"
        )
        self._score_btn.setMinimumHeight(48)
        self._score_btn.clicked.connect(self._on_run_score)
        btn_layout.addWidget(self._score_btn)

        self._trends_btn = QPushButton("Refresh Trends")
        self._trends_btn.setStyleSheet(
            "background-color: #cba6f7; color: #1e1e2e; font-weight: bold; "
            "padding: 12px 24px;"
        )
        self._trends_btn.setMinimumHeight(48)
        self._trends_btn.clicked.connect(self._on_refresh_trends)
        btn_layout.addWidget(self._trends_btn)

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
                background-color: #89b4fa;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self._progress_bar)

        # --- Score display ---
        score_group = QGroupBox("Network Score")
        score_layout = QVBoxLayout(score_group)

        # Big score number
        self._score_label = QLabel("--")
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_label.setStyleSheet(
            "font-size: 64px; font-weight: bold; color: #585b70; padding: 8px;"
        )
        score_layout.addWidget(self._score_label)

        self._grade_label = QLabel("Run a benchmark to see your network score")
        self._grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_label.setStyleSheet("font-size: 14px; color: #a6adc8; padding: 4px;")
        self._grade_label.setWordWrap(True)
        score_layout.addWidget(self._grade_label)

        # Sub-score cards
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
        self._history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        history_layout.addWidget(self._history_table)
        main_layout.addWidget(history_group)

        # --- Patterns / alerts ---
        patterns_group = QGroupBox("Detected Patterns")
        patterns_layout = QVBoxLayout(patterns_group)

        self._patterns_label = QLabel("Run a few benchmarks over time to detect patterns.")
        self._patterns_label.setWordWrap(True)
        self._patterns_label.setStyleSheet("color: #a6adc8; padding: 8px; font-size: 13px;")
        patterns_layout.addWidget(self._patterns_label)

        main_layout.addWidget(patterns_group)

        # --- Metric trend table ---
        metric_group = QGroupBox("Metric Trends")
        metric_layout = QVBoxLayout(metric_group)

        self._metric_table = QTableWidget(0, 6)
        self._metric_table.setHorizontalHeaderLabels([
            "Metric", "Current", "Average", "Best", "Worst", "Trend",
        ])
        self._metric_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._metric_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._metric_table.setAlternatingRowColors(True)
        self._metric_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
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
            return "#a6e3a1"  # green
        if score >= 75:
            return "#89b4fa"  # blue
        if score >= 60:
            return "#f9e2af"  # yellow
        if score >= 40:
            return "#fab387"  # orange
        return "#f38ba8"      # red

    # ------------------------------------------------------------------
    # Score actions
    # ------------------------------------------------------------------

    def _on_run_score(self):
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
            f"font-size: 64px; font-weight: bold; color: {color}; padding: 8px;"
        )

        self._grade_label.setText(
            f"Grade {score.grade} — {score.rating}"
        )
        self._grade_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {color}; padding: 4px;"
        )

        # Clear old sub-score cards
        for card in self._subscore_cards.values():
            self._subscore_grid.removeWidget(card)
            card.deleteLater()
        self._subscore_cards.clear()

        # Create new sub-score cards
        for i, sub in enumerate(score.sub_scores):
            card = QLabel(
                f"{sub.name}\n{sub.value:.0f}/100\n{sub.raw_value:.1f}{sub.raw_unit}"
            )
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub_color = self._score_color(sub.value)
            card.setStyleSheet(f"""
                background-color: #2a2a3d;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 10px;
                font-size: 11px;
                color: {sub_color};
            """)
            card.setMinimumHeight(70)
            card.setWordWrap(True)
            row, col = divmod(i, 3)
            self._subscore_grid.addWidget(card, row, col)
            self._subscore_cards[sub.name] = card

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def _on_refresh_trends(self):
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

        # If we have a current score from trends, update the display
        if summary.current_score is not None and not self._subscore_cards:
            color = self._score_color(summary.current_score)
            self._score_label.setText(f"{summary.current_score:.0f}")
            self._score_label.setStyleSheet(
                f"font-size: 64px; font-weight: bold; color: {color}; padding: 8px;"
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
            ts = b.get("timestamp", "--")[:19]
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
                if col >= 2:
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
                    "No concerning patterns detected. Your network is stable."
                )
                self._patterns_label.setStyleSheet(
                    "color: #a6e3a1; padding: 8px; font-size: 13px;"
                )
            else:
                count_needed = 5 - summary.snapshot_count
                self._patterns_label.setText(
                    f"Need {count_needed} more benchmark(s) to detect patterns. "
                    f"Run 'Run Score Benchmark' a few more times."
                )
                self._patterns_label.setStyleSheet(
                    "color: #a6adc8; padding: 8px; font-size: 13px;"
                )
            return

        _ICONS = {
            "degradation": "\u26a0",   # warning
            "time_of_day": "\u23f0",   # alarm clock
            "improving": "\u2714",     # checkmark
            "volatile": "\u2194",      # left-right arrow
            "stable": "\u2022",        # bullet
        }
        _COLORS = {
            "degradation": "#f38ba8",
            "time_of_day": "#f9e2af",
            "improving": "#a6e3a1",
            "volatile": "#fab387",
        }

        lines = []
        for p in summary.patterns:
            icon = _ICONS.get(p.pattern_type, "\u2022")
            lines.append(f"{icon}  {p.description}")

        color = "#f9e2af"  # default to warning yellow
        for p in summary.patterns:
            if p.pattern_type == "degradation":
                color = "#f38ba8"
                break

        self._patterns_label.setText("\n".join(lines))
        self._patterns_label.setStyleSheet(
            f"color: {color}; padding: 8px; font-size: 13px;"
        )

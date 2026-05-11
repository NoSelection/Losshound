"""Optimizer tab — one-click network performance tuning with DNS benchmarking."""

from __future__ import annotations

import logging
from dataclasses import asdict
from functools import partial

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from losshound.core.benchmark import (
    BenchmarkReport,
    BenchmarkSnapshot,
    compare_snapshots,
    get_latest_snapshot,
    run_benchmark,
    save_snapshot,
)
from losshound.core.dns_bench import DnsBenchmarkResult
from losshound.core.optimizer import (
    NetworkOptimizer, OptimizeReport, OptimizeResult,
)
from losshound.gui.theme import button_style
from losshound.gui.widgets import TelemetryHeader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _DnsBenchmarkWorker(QThread):
    """Run DNS benchmark in a background thread."""

    finished = Signal(list)  # list[DnsBenchmarkResult]
    progress = Signal(str)

    def run(self):
        try:
            opt = NetworkOptimizer()
            self.progress.emit("Benchmarking DNS servers...")
            results = opt.benchmark_dns()
            self.finished.emit(results)
        except Exception as exc:
            logger.error("DNS benchmark failed: %s", exc)
            self.finished.emit([])


class _OptimizeWorker(QThread):
    """Run full optimization in a background thread."""

    finished = Signal(object)  # OptimizeReport
    progress = Signal(str)

    def __init__(self, skip_dns: bool = False, skip_mtu: bool = False):
        super().__init__()
        self._skip_dns = skip_dns
        self._skip_mtu = skip_mtu

    def run(self):
        try:
            opt = NetworkOptimizer()
            self.progress.emit("Creating backup...")
            self.progress.emit("Optimizing network stack...")
            report = opt.optimize_all(
                skip_dns=self._skip_dns, skip_mtu=self._skip_mtu,
            )
            self.finished.emit(report)
        except Exception as exc:
            logger.error("Optimization failed: %s", exc)
            self.finished.emit(None)


class _RestoreWorker(QThread):
    """Restore settings from backup in a background thread."""

    finished = Signal(list)  # list[OptimizeResult]
    progress = Signal(str)

    def run(self):
        try:
            opt = NetworkOptimizer()
            self.progress.emit("Restoring backup...")
            results = opt.restore_backup()
            self.finished.emit(results)
        except Exception as exc:
            logger.error("Restore failed: %s", exc)
            self.finished.emit([])


class _BenchmarkWorker(QThread):
    """Run network benchmark in a background thread."""

    finished = Signal(object)  # BenchmarkSnapshot
    progress = Signal(str)

    def __init__(self, label: str = "snapshot"):
        super().__init__()
        self._label = label

    def run(self):
        try:
            snapshot = run_benchmark(
                label=self._label,
                ping_count=20,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            save_snapshot(snapshot)
            self.finished.emit(snapshot)
        except Exception as exc:
            logger.error("Benchmark failed: %s", exc)
            self.finished.emit(None)


class _StatusWorker(QThread):
    """Fetch current optimization status in background."""

    finished = Signal(dict)

    def run(self):
        try:
            opt = NetworkOptimizer()
            status = opt.get_optimization_status()
            self.finished.emit(status)
        except Exception as exc:
            logger.error("Status check failed: %s", exc)
            self.finished.emit({})


# ---------------------------------------------------------------------------
# Optimizer Tab
# ---------------------------------------------------------------------------

class OptimizerTab(QWidget):
    """Network performance optimizer tab."""

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
            "Network Performance Optimizer",
            "Tune TCP/IP, benchmark DNS, optimize MTU, and manage Windows throttling from one console.",
            "OPTIMIZER",
            "ADMIN READY" if NetworkOptimizer.check_admin() else "LIMITED",
            "#75c884",
        ))

        # --- Admin status ---
        self._admin_label = QLabel()
        self._admin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._admin_label)
        self._update_admin_label()

        # --- Action buttons ---
        btn_group = QGroupBox("Actions")
        btn_layout = QGridLayout(btn_group)
        btn_layout.setSpacing(8)

        self._optimize_btn = QPushButton("Optimize All")
        self._optimize_btn.setStyleSheet(button_style("success"))
        self._optimize_btn.setMinimumHeight(42)
        self._optimize_btn.clicked.connect(self._on_optimize_all)
        btn_layout.addWidget(self._optimize_btn, 0, 0)

        self._dns_bench_btn = QPushButton("Benchmark DNS")
        self._dns_bench_btn.setStyleSheet(button_style("primary"))
        self._dns_bench_btn.setMinimumHeight(42)
        self._dns_bench_btn.clicked.connect(self._on_dns_benchmark)
        btn_layout.addWidget(self._dns_bench_btn, 0, 1)

        self._restore_btn = QPushButton("Revert All Changes")
        self._restore_btn.setStyleSheet(button_style("danger"))
        self._restore_btn.setMinimumHeight(42)
        self._restore_btn.setToolTip(
            "Undo ALL optimizations and restore your original network settings"
        )
        self._restore_btn.clicked.connect(self._on_restore)
        btn_layout.addWidget(self._restore_btn, 0, 2)

        self._status_btn = QPushButton("Check Status")
        self._status_btn.setMinimumHeight(42)
        self._status_btn.clicked.connect(self._on_check_status)
        btn_layout.addWidget(self._status_btn, 0, 3)

        # Row 2: Benchmark buttons
        self._bench_before_btn = QPushButton("Benchmark BEFORE")
        self._bench_before_btn.setStyleSheet(button_style("primary"))
        self._bench_before_btn.setMinimumHeight(42)
        self._bench_before_btn.setToolTip(
            "Run a full network benchmark BEFORE optimization to measure baseline"
        )
        self._bench_before_btn.clicked.connect(lambda: self._on_benchmark("before"))
        btn_layout.addWidget(self._bench_before_btn, 1, 0)

        self._bench_after_btn = QPushButton("Benchmark AFTER")
        self._bench_after_btn.setStyleSheet(button_style("primary"))
        self._bench_after_btn.setMinimumHeight(42)
        self._bench_after_btn.setToolTip(
            "Run a full network benchmark AFTER optimization to measure improvement"
        )
        self._bench_after_btn.clicked.connect(lambda: self._on_benchmark("after"))
        btn_layout.addWidget(self._bench_after_btn, 1, 1)

        self._compare_btn = QPushButton("Compare Before vs After")
        self._compare_btn.setStyleSheet(button_style("warning"))
        self._compare_btn.setMinimumHeight(42)
        self._compare_btn.setToolTip("Compare your before and after benchmarks")
        self._compare_btn.clicked.connect(self._on_compare)
        btn_layout.addWidget(self._compare_btn, 1, 2, 1, 2)  # span 2 columns

        main_layout.addWidget(btn_group)

        # --- Progress ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Idle")
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1d222b;
                border: 1px solid #3a4350;
                border-radius: 2px;
                text-align: center;
                color: #d8dee9;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #62c7d8;
                border-radius: 0;
            }
        """)
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        main_layout.addWidget(self._progress_bar)

        # --- Current status cards ---
        status_group = QGroupBox("Current Settings")
        self._status_grid = QGridLayout(status_group)
        self._status_grid.setSpacing(8)

        self._status_cards: dict[str, QLabel] = {}
        card_defs = [
            ("admin", "Privileges"),
            ("tcp_tuning", "TCP Auto-Tuning"),
            ("congestion", "Congestion Provider"),
            ("ecn", "ECN"),
            ("rss", "RSS"),
            ("dns", "DNS Servers"),
            ("mtu", "MTU"),
            ("throttling", "Network Throttling"),
        ]
        for i, (key, label) in enumerate(card_defs):
            card = self._make_status_card(label)
            self._status_cards[key] = card
            row, col = divmod(i, 4)
            self._status_grid.addWidget(card, row, col)

        main_layout.addWidget(status_group)

        # --- DNS Benchmark results table ---
        dns_group = QGroupBox("DNS Benchmark Results")
        dns_layout = QVBoxLayout(dns_group)

        self._dns_table = QTableWidget(0, 6)
        self._dns_table.setHorizontalHeaderLabels([
            "Rank", "Server", "Provider", "Avg (ms)", "Min (ms)", "Success %",
        ])
        self._dns_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._dns_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dns_table.setAlternatingRowColors(True)
        self._dns_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        dns_layout.addWidget(self._dns_table)
        main_layout.addWidget(dns_group)

        # --- Optimization results table ---
        results_group = QGroupBox("Optimization Results")
        results_layout = QVBoxLayout(results_group)

        self._results_table = QTableWidget(0, 5)
        self._results_table.setHorizontalHeaderLabels([
            "Optimization", "Status", "Before", "After", "Note",
        ])
        self._results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        results_layout.addWidget(self._results_table)
        main_layout.addWidget(results_group)

        # --- Benchmark comparison table ---
        bench_group = QGroupBox("Performance Benchmark — Before vs After")
        bench_layout = QVBoxLayout(bench_group)

        self._bench_table = QTableWidget(0, 4)
        self._bench_table.setHorizontalHeaderLabels([
            "Metric", "Before", "After", "Change",
        ])
        self._bench_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._bench_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bench_table.setAlternatingRowColors(True)
        self._bench_table.setStyleSheet("""
            QTableWidget { alternate-background-color: #252538; }
        """)
        bench_layout.addWidget(self._bench_table)

        self._bench_summary_label = QLabel("")
        self._bench_summary_label.setWordWrap(True)
        self._bench_summary_label.setStyleSheet(
            "padding: 8px; font-size: 13px; color: #d8dee9;"
        )
        bench_layout.addWidget(self._bench_summary_label)

        main_layout.addWidget(bench_group)

        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Initial status check
        self._on_check_status()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_status_card(self, label: str) -> QLabel:
        """Create a styled status card widget."""
        card = QLabel(f"{label}\n--")
        card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.setStyleSheet("""
            background-color: #1b2028;
            border: 1px solid #3a4350;
            border-radius: 2px;
            padding: 12px;
            font-size: 12px;
            color: #d8dee9;
        """)
        card.setMinimumHeight(70)
        card.setWordWrap(True)
        return card

    def _update_admin_label(self):
        is_admin = NetworkOptimizer.check_admin()
        if is_admin:
            self._admin_label.setText("Running as Administrator — all optimizations available")
            self._admin_label.setStyleSheet(
                "color: #75c884; font-weight: bold; padding: 4px;"
            )
        else:
            self._admin_label.setText(
                "Running without Administrator — some optimizations will be skipped. "
                "Re-launch as Admin for full optimization."
            )
            self._admin_label.setStyleSheet(
                "color: #d9b65f; font-weight: bold; padding: 4px;"
            )

    def _set_busy(self, busy: bool, message: str = ""):
        """Toggle button states and progress bar."""
        self._optimize_btn.setEnabled(not busy)
        self._dns_bench_btn.setEnabled(not busy)
        self._restore_btn.setEnabled(not busy)
        self._status_btn.setEnabled(not busy)
        self._bench_before_btn.setEnabled(not busy)
        self._bench_after_btn.setEnabled(not busy)
        self._compare_btn.setEnabled(not busy)

        if busy:
            self._progress_bar.setRange(0, 0)  # indeterminate
            self._progress_bar.setFormat(message or "Working...")
        else:
            self._progress_bar.setRange(0, 1)
            self._progress_bar.setValue(1)
            self._progress_bar.setFormat(message or "Done")

    def _update_status_card(self, key: str, title: str, value: str, status: str = "neutral"):
        card = self._status_cards.get(key)
        if not card:
            return

        colors = {
            "healthy": "#75c884",
            "warning": "#d9b65f",
            "error": "#e06363",
            "neutral": "#d8dee9",
        }
        color = colors.get(status, "#d8dee9")
        card.setText(f"{title}\n{value}")
        card.setStyleSheet(f"""
            background-color: #1b2028;
            border: 1px solid #3a4350;
            border-radius: 2px;
            padding: 12px;
            font-size: 12px;
            color: {color};
        """)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_optimize_all(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        reply = QMessageBox.question(
            self, "Optimize All",
            "This will modify your network settings to optimize performance.\n"
            "A backup will be created first so you can restore later.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, "Optimizing network...")
        self._worker = _OptimizeWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_optimize_done)
        self._worker.start()

    def _on_optimize_done(self, report: OptimizeReport | None):
        self._worker = None
        if report is None:
            self._set_busy(False, "Optimization failed")
            QMessageBox.warning(self, "Error", "Optimization failed. Check logs for details.")
            return

        self._set_busy(False, report.summary)
        self._populate_results_table(report.results)
        self._on_check_status()  # refresh status cards

        QMessageBox.information(
            self, "Optimization Complete",
            f"{report.summary}\n\n"
            f"Backup saved — you can restore your original settings anytime.",
        )

    def _on_dns_benchmark(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        self._set_busy(True, "Benchmarking DNS servers...")
        self._worker = _DnsBenchmarkWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_dns_benchmark_done)
        self._worker.start()

    def _on_dns_benchmark_done(self, results: list[DnsBenchmarkResult]):
        self._worker = None
        if not results:
            self._set_busy(False, "DNS benchmark failed")
            return

        self._set_busy(False, f"DNS benchmark complete — fastest: {results[0].name}")
        self._populate_dns_table(results)

    def _on_restore(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        reply = QMessageBox.question(
            self, "Revert All Changes",
            "This will REVERT all optimizations and restore your original\n"
            "network settings from before optimization was applied.\n\n"
            "Everything will go back to exactly how it was:\n"
            "  - DNS servers\n"
            "  - TCP/IP settings\n"
            "  - MTU\n"
            "  - Network throttling\n"
            "  - Nagle's algorithm\n"
            "  - Adapter power management\n"
            "  - Interrupt moderation\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, "Reverting all changes...")
        self._worker = _RestoreWorker()
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(self._on_restore_done)
        self._worker.start()

    def _on_restore_done(self, results: list[OptimizeResult]):
        self._worker = None
        if not results:
            self._set_busy(False, "Revert failed — no backup found")
            QMessageBox.warning(
                self, "Revert",
                "No backup found. You need to run Optimize first before you can revert.",
            )
            return

        succeeded = sum(1 for r in results if r.success)
        skipped = sum(
            1 for r in results
            if not r.success and r.needs_admin and r.error and "Administrator" in r.error
        )
        self._set_busy(False, f"Reverted {succeeded}/{len(results)} settings")
        self._populate_results_table(results)
        self._on_check_status()

        msg = f"Reverted {succeeded}/{len(results)} settings to their original values."
        if skipped:
            msg += f"\n\n{skipped} settings could not be reverted (requires Administrator)."
        QMessageBox.information(self, "Revert Complete", msg)

    def _on_check_status(self):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        self._worker = _StatusWorker()
        self._worker.finished.connect(self._on_status_done)
        self._worker.start()

    def _on_status_done(self, status: dict):
        self._worker = None
        if not status:
            return

        # Admin
        is_admin = status.get("admin", False)
        self._update_status_card(
            "admin", "Privileges",
            "Administrator" if is_admin else "Standard User",
            "healthy" if is_admin else "warning",
        )

        # TCP settings
        tcp = status.get("tcp", {})

        tuning = tcp.get("auto_tuning_level", "unknown")
        self._update_status_card(
            "tcp_tuning", "TCP Auto-Tuning", tuning,
            "healthy" if tuning.lower() == "normal" else "warning",
        )

        congestion = tcp.get("congestion_provider", "unknown")
        self._update_status_card(
            "congestion", "Congestion Provider", congestion,
            "healthy" if "ctcp" in congestion.lower() else "neutral",
        )

        ecn = tcp.get("ecn_capability", "unknown")
        self._update_status_card(
            "ecn", "ECN", ecn,
            "healthy" if ecn.lower() == "enabled" else "neutral",
        )

        rss = tcp.get("rss", "unknown")
        self._update_status_card(
            "rss", "RSS", rss,
            "healthy" if rss.lower() == "enabled" else "neutral",
        )

        # DNS
        primary = status.get("dns_primary", "")
        secondary = status.get("dns_secondary", "")
        dns_text = primary or "auto"
        if secondary:
            dns_text += f"\n{secondary}"
        self._update_status_card("dns", "DNS Servers", dns_text, "neutral")

        # MTU
        mtu = status.get("mtu", 1500)
        self._update_status_card(
            "mtu", "MTU", str(mtu),
            "healthy" if 1400 <= mtu <= 1500 else "warning",
        )

        # Throttling
        throttling = status.get("network_throttling_index")
        if throttling is None:
            thr_text = "default"
            thr_status = "warning"
        elif throttling == 0xFFFFFFFF or throttling == -1:
            thr_text = "disabled"
            thr_status = "healthy"
        else:
            thr_text = f"enabled ({throttling})"
            thr_status = "warning"
        self._update_status_card("throttling", "Network Throttling", thr_text, thr_status)

    # ------------------------------------------------------------------
    # Benchmark actions
    # ------------------------------------------------------------------

    def _on_benchmark(self, label: str):
        if self._worker is not None and self._worker.isRunning():
            return  # already running, ignore the click
        self._set_busy(True, f"Running {label} benchmark (this takes ~60s)...")
        self._worker = _BenchmarkWorker(label=label)
        self._worker.progress.connect(
            lambda msg: self._progress_bar.setFormat(msg),
        )
        self._worker.finished.connect(
            lambda snap: self._on_benchmark_done(snap, label),
        )
        self._worker.start()

    def _on_benchmark_done(self, snapshot: BenchmarkSnapshot | None, label: str):
        self._worker = None
        if snapshot is None:
            self._set_busy(False, "Benchmark failed")
            QMessageBox.warning(self, "Benchmark", "Benchmark failed. Check logs.")
            return

        self._set_busy(
            False,
            f"{label.upper()} benchmark complete — "
            f"latency: {snapshot.avg_latency_ms:.1f}ms, "
            f"jitter: {snapshot.avg_jitter_ms:.1f}ms"
            if snapshot.avg_latency_ms and snapshot.avg_jitter_ms
            else f"{label.upper()} benchmark complete",
        )

        msg = (
            f"Benchmark '{label}' saved!\n\n"
            f"  Avg latency:  {snapshot.avg_latency_ms:.1f} ms\n"
            f"  Avg jitter:   {snapshot.avg_jitter_ms:.1f} ms\n"
            f"  Avg loss:     {snapshot.avg_loss_pct:.1f}%\n"
            f"  Avg DNS:      {snapshot.avg_dns_ms:.1f} ms\n"
            f"  Avg TCP:      {snapshot.avg_tcp_ms:.1f} ms"
            if all(v is not None for v in [
                snapshot.avg_latency_ms, snapshot.avg_jitter_ms,
                snapshot.avg_loss_pct, snapshot.avg_dns_ms, snapshot.avg_tcp_ms,
            ])
            else f"Benchmark '{label}' saved!"
        )

        if label == "before":
            msg += "\n\nNow run 'Optimize All', then click 'Benchmark AFTER'."
        elif label == "after":
            msg += "\n\nClick 'Compare Before vs After' to see the difference!"

        QMessageBox.information(self, "Benchmark Complete", msg)

    def _on_compare(self):
        before = get_latest_snapshot("before")
        after = get_latest_snapshot("after")

        if not before:
            QMessageBox.warning(
                self, "Compare",
                "No 'before' benchmark found.\n"
                "Click 'Benchmark BEFORE' first.",
            )
            return
        if not after:
            QMessageBox.warning(
                self, "Compare",
                "No 'after' benchmark found.\n"
                "Click 'Benchmark AFTER' first.",
            )
            return

        report = compare_snapshots(before, after)
        self._populate_bench_table(report)

    def _populate_bench_table(self, report: BenchmarkReport):
        """Fill the benchmark comparison table."""
        b = report.before
        a = report.after
        d = report.delta

        def _fmt(val, suffix="ms"):
            return f"{val:.1f}{suffix}" if val is not None else "N/A"

        def _change(diff, pct, lower_better=True):
            if diff is None:
                return "", "neutral"
            sign = "+" if diff > 0 else ""
            text = f"{sign}{diff:.1f}ms ({sign}{pct:.1f}%)" if pct is not None else f"{sign}{diff:.1f}"
            if pct is not None and abs(pct) >= 2:
                if (diff < 0) == lower_better:
                    return text, "healthy"
                return text, "error"
            return text, "neutral"

        rows = [
            ("Avg Latency", _fmt(b.avg_latency_ms), _fmt(a.avg_latency_ms),
             *_change(d.latency_delta_ms, d.latency_pct_change)),
            ("Avg Jitter", _fmt(b.avg_jitter_ms), _fmt(a.avg_jitter_ms),
             *_change(d.jitter_delta_ms, d.jitter_pct_change)),
            ("Avg Packet Loss", _fmt(b.avg_loss_pct, "%"), _fmt(a.avg_loss_pct, "%"),
             *(lambda: (
                 f"{'+' if d.loss_delta_pct > 0 else ''}{d.loss_delta_pct:.1f}pp",
                 "healthy" if d.loss_delta_pct < -0.5 else ("error" if d.loss_delta_pct > 0.5 else "neutral"),
             ) if d.loss_delta_pct is not None else ("N/A", "neutral"))()),
            ("Avg DNS Resolve", _fmt(b.avg_dns_ms), _fmt(a.avg_dns_ms),
             *_change(d.dns_delta_ms, d.dns_pct_change)),
            ("Avg TCP Connect", _fmt(b.avg_tcp_ms), _fmt(a.avg_tcp_ms),
             *_change(d.tcp_delta_ms, d.tcp_pct_change)),
        ]

        # Add per-target ping rows
        after_map = {p.target: p for p in a.ping_results}
        for bp in b.ping_results:
            ap = after_map.get(bp.target)
            b_ms = _fmt(bp.avg_ms)
            a_ms = _fmt(ap.avg_ms) if ap else "N/A"
            if bp.avg_ms is not None and ap and ap.avg_ms is not None:
                diff = ap.avg_ms - bp.avg_ms
                pct = (diff / bp.avg_ms * 100.0) if bp.avg_ms else 0
                change_text, change_status = _change(diff, pct)
            else:
                change_text, change_status = "N/A", "neutral"
            rows.append((f"  Ping {bp.target}", b_ms, a_ms, change_text, change_status))

        colors = {
            "healthy": Qt.GlobalColor.green,
            "error": Qt.GlobalColor.red,
            "neutral": Qt.GlobalColor.white,
        }

        self._bench_table.setRowCount(len(rows))
        for row_idx, (metric, before_val, after_val, change_text, status) in enumerate(rows):
            items = [
                QTableWidgetItem(metric),
                QTableWidgetItem(before_val),
                QTableWidgetItem(after_val),
                QTableWidgetItem(change_text),
            ]
            # Color the change column
            items[3].setForeground(colors.get(status, Qt.GlobalColor.white))
            # Bold aggregate rows
            if not metric.startswith("  "):
                for item in items:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

            for col, item in enumerate(items):
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._bench_table.setItem(row_idx, col, item)

        self._bench_summary_label.setText(f"Result: {report.summary}")

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_dns_table(self, results: list[DnsBenchmarkResult]):
        self._dns_table.setRowCount(len(results))
        for row, r in enumerate(results):
            rank_item = QTableWidgetItem(str(row + 1))
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            server_item = QTableWidgetItem(r.server)
            name_item = QTableWidgetItem(r.name)

            avg_item = QTableWidgetItem(
                f"{r.avg_ms:.1f}" if r.avg_ms != float("inf") else "N/A",
            )
            avg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            min_item = QTableWidgetItem(
                f"{r.min_ms:.1f}" if r.min_ms != float("inf") else "N/A",
            )
            min_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            success_item = QTableWidgetItem(f"{r.success_rate * 100:.0f}%")
            success_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Color-code the row based on ranking
            if row == 0:
                for item in (rank_item, server_item, name_item, avg_item, min_item, success_item):
                    item.setForeground(Qt.GlobalColor.green)
            elif r.success_rate < 0.5:
                for item in (rank_item, server_item, name_item, avg_item, min_item, success_item):
                    item.setForeground(Qt.GlobalColor.red)

            self._dns_table.setItem(row, 0, rank_item)
            self._dns_table.setItem(row, 1, server_item)
            self._dns_table.setItem(row, 2, name_item)
            self._dns_table.setItem(row, 3, avg_item)
            self._dns_table.setItem(row, 4, min_item)
            self._dns_table.setItem(row, 5, success_item)

    def _populate_results_table(self, results: list[OptimizeResult]):
        _STATUS_COLORS = {
            "Applied": Qt.GlobalColor.green,
            "Verified": Qt.GlobalColor.cyan,
            "No change": Qt.GlobalColor.white,
            "Skipped": Qt.GlobalColor.yellow,
            "Failed": Qt.GlobalColor.red,
            "Unsupported": Qt.GlobalColor.darkYellow,
            "Reboot required": Qt.GlobalColor.magenta,
        }

        self._results_table.setRowCount(len(results))
        for row, r in enumerate(results):
            name_item = QTableWidgetItem(r.name)

            # Use the new status field; fall back to legacy logic for
            # results that haven't been migrated yet.
            status_text = r.status
            if not status_text:
                if r.success:
                    status_text = "Applied"
                elif r.needs_admin and r.error and "Administrator" in r.error:
                    status_text = "Skipped"
                else:
                    status_text = "Failed"

            color = _STATUS_COLORS.get(status_text, Qt.GlobalColor.white)
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(color)

            before_item = QTableWidgetItem(r.before or "--")
            after_item = QTableWidgetItem(r.after or "--")
            note_item = QTableWidgetItem(r.note or r.error or "")

            self._results_table.setItem(row, 0, name_item)
            self._results_table.setItem(row, 1, status_item)
            self._results_table.setItem(row, 2, before_item)
            self._results_table.setItem(row, 3, after_item)
            self._results_table.setItem(row, 4, note_item)

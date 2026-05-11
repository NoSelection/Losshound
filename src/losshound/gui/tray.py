"""System tray icon with live network status and notifications."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from losshound.core.models import Diagnosis, DiagnosisCategory, Observation

logger = logging.getLogger(__name__)


def _create_status_icon(color: str, size: int = 64) -> QIcon:
    """Create a simple colored circle icon for the tray."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor(color).darker(130))
    margin = size // 8
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()

    return QIcon(pixmap)


# Pre-built icons for each status
_ICONS = {
    "healthy":  "#a6e3a1",  # green
    "warning":  "#f9e2af",  # yellow
    "error":    "#f38ba8",  # red
    "unknown":  "#6c7086",  # grey
}


class TrayIcon(QSystemTrayIcon):
    """System tray icon that shows network health at a glance.

    Signals
    -------
    show_requested:
        Emitted when the user clicks "Show Window" in the tray menu.
    quit_requested:
        Emitted when the user clicks "Quit" in the tray menu.
    """

    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None,
                 engine: "Optional[object]" = None):
        super().__init__(parent)
        self._last_status = "unknown"
        self._notifications_enabled = True
        self._engine = engine

        # Build icons
        self._status_icons = {
            key: _create_status_icon(color)
            for key, color in _ICONS.items()
        }

        self.setIcon(self._status_icons["unknown"])
        self.setToolTip("Losshound — Starting up...")

        # Context menu
        menu = QMenu()

        self._status_action = QAction("Status: starting...", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)

        menu.addSeparator()

        show_action = QAction("Show Window", menu)
        show_action.triggered.connect(self.show_requested.emit)
        menu.addAction(show_action)

        self._notif_action = QAction("Disable Notifications", menu)
        self._notif_action.triggered.connect(self._toggle_notifications)
        menu.addAction(self._notif_action)

        snooze_action = QAction("Snooze alerts", menu)
        snooze_action.triggered.connect(self._snooze_clicked)
        menu.addAction(snooze_action)

        self._recent_menu = QMenu("Recent Alerts", menu)
        self._recent_menu.aboutToShow.connect(self._refresh_recent_alerts)
        menu.addMenu(self._recent_menu)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

        # Double-click to show
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()

    def _toggle_notifications(self):
        self._notifications_enabled = not self._notifications_enabled
        self._notif_action.setText(
            "Enable Notifications" if not self._notifications_enabled
            else "Disable Notifications"
        )

    def update_observation(self, obs: Observation):
        """Update tray icon and tooltip from a live observation."""
        # Compute quick status
        losses = []
        rtts = []

        if obs.gateway_ping:
            losses.append(obs.gateway_ping.loss_percent)
            if obs.gateway_ping.rtt_avg is not None:
                rtts.append(obs.gateway_ping.rtt_avg)

        for p in obs.public_pings:
            losses.append(p.loss_percent)
            if p.rtt_avg is not None:
                rtts.append(p.rtt_avg)

        avg_loss = sum(losses) / len(losses) if losses else 0
        avg_rtt = sum(rtts) / len(rtts) if rtts else 0

        # Determine status
        if avg_loss > 20 or avg_rtt > 200:
            status = "error"
        elif avg_loss > 5 or avg_rtt > 100:
            status = "warning"
        elif losses:
            status = "healthy"
        else:
            status = "unknown"

        self._last_status = status
        self.setIcon(self._status_icons[status])

        # Tooltip
        loss_str = f"{avg_loss:.0f}%" if losses else "N/A"
        rtt_str = f"{avg_rtt:.0f}ms" if rtts else "N/A"
        tip = f"Losshound — Loss: {loss_str} | Latency: {rtt_str}"
        self.setToolTip(tip)
        self._status_action.setText(f"Loss: {loss_str} | Latency: {rtt_str}")

    def update_diagnosis(self, diag: Diagnosis):
        """Route the diagnosis through the AlertEngine (if set)."""
        if not self._notifications_enabled:
            return
        if self._engine is None:
            return

        event = self._engine.feed(diag)
        if event is None:
            return

        if event.is_resolution:
            icon = QSystemTrayIcon.MessageIcon.Information
        elif event.severity == "critical":
            icon = QSystemTrayIcon.MessageIcon.Critical
        else:
            icon = QSystemTrayIcon.MessageIcon.Warning

        self.showMessage(
            f"Losshound — {event.title}",
            event.message,
            icon,
            5000,
        )

    def _snooze_clicked(self):
        if self._engine is None:
            return
        seconds = self._engine.snooze()
        minutes = max(1, round(seconds / 60))
        self.showMessage(
            "Losshound",
            f"Alerts snoozed for {minutes} minute{'s' if minutes != 1 else ''}.",
            QSystemTrayIcon.MessageIcon.Information, 2500,
        )

    def _refresh_recent_alerts(self):
        self._recent_menu.clear()
        rows = self._engine.recent_alerts(10) if self._engine is not None else []
        if not rows:
            placeholder = QAction("(no alerts)", self._recent_menu)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
            return
        for r in rows:
            label = f"{r.timestamp[:19]} — {r.title}"
            if r.resolved_at:
                label += " ✓"
            act = QAction(label, self._recent_menu)
            act.setEnabled(False)
            self._recent_menu.addAction(act)

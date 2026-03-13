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

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._last_status = "unknown"
        self._notifications_enabled = True

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
        """Show a notification if network issues are detected."""
        if not self._notifications_enabled:
            return

        # Only notify on transitions to bad states
        if diag.category in (
            DiagnosisCategory.LAN_ISSUE,
            DiagnosisCategory.ISP_WAN_ISSUE,
            DiagnosisCategory.DNS_ISSUE,
        ):
            self.showMessage(
                f"Losshound — {diag.category.display_name}",
                diag.summary,
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
        elif diag.category == DiagnosisCategory.INTERMITTENT:
            self.showMessage(
                "Losshound — Intermittent Issues",
                diag.summary,
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

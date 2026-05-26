from __future__ import annotations

from math import cos, sin, tau
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from losshound.gui.branding import losshound_pixmap
from losshound.gui.painted import (
    BracketedPanel,
    HeaderHalo,
    LiveDot,
    Sparkline,
)
from losshound.gui.palette import (
    FONT_CHROME_FAMILIES,
    FONT_MONO_FAMILIES,
    c,
    chrome_font,
    label_font,
    mono_font,
    qc,
)


# ---------------------------------------------------------------------------
# Top-of-window header
# ---------------------------------------------------------------------------


class LosshoundHeader(QWidget):
    """Top app rail: logo + wordmark + halo + window/monitor actions."""

    pause_clicked = Signal()
    run_now_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("losshound-header")
        self.setFixedHeight(84)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        # Stack: halo background overlay + foreground row.
        self._halo = HeaderHalo(self)
        self._halo.setGeometry(0, 0, 1, 1)  # resized in resizeEvent

        row = QHBoxLayout(self)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(16)

        # Brand block (logo + wordmark)
        mark = QLabel(self)
        mark.setPixmap(losshound_pixmap(56))
        mark.setFixedSize(60, 60)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(mark)

        text_stack = QVBoxLayout()
        text_stack.setContentsMargins(0, 0, 0, 0)
        text_stack.setSpacing(0)

        title = QLabel("Losshound")
        title.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 31px; font-weight: 700; letter-spacing: 1px;"
        )
        text_stack.addWidget(title)

        subtitle = QLabel("Network Diagnosis")
        subtitle.setStyleSheet(
            f"color: {c('info')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px; font-weight: 500; letter-spacing: 3px;"
        )
        subtitle.setText("NETWORK DIAGNOSIS")
        text_stack.addWidget(subtitle)
        row.addLayout(text_stack)

        row.addStretch()

        # Action group — Pause / Run Now / Settings cog.
        self._pause_btn = QPushButton("▶  Pause monitor")
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.setText("▶  PAUSE MONITOR")
        self._pause_btn.setStyleSheet(_header_button_qss(primary=True))
        self._pause_btn.clicked.connect(self.pause_clicked.emit)
        row.addWidget(self._pause_btn)

        self._run_btn = QPushButton("STEP")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(_header_button_qss(primary=False))
        self._run_btn.clicked.connect(self.run_now_clicked.emit)
        row.addWidget(self._run_btn)

        cog = QPushButton("⚙")
        cog.setCursor(Qt.CursorShape.PointingHandCursor)
        cog.setFixedSize(QSize(40, 36))
        cog.setText("")
        cog.setIcon(_gear_icon())
        cog.setIconSize(QSize(18, 18))
        cog.setStyleSheet(_header_cog_qss())
        cog.clicked.connect(self.settings_clicked.emit)
        row.addWidget(cog)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._pause_btn.setText("▶  Resume monitor")
        else:
            self._pause_btn.setText("▶  Pause monitor")

        self._pause_btn.setText(
            "▶  RESUME MONITOR" if paused else "▶  PAUSE MONITOR"
        )

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        # Stretch the halo across the upper-middle of the header.
        halo_w = int(self.width() * 0.55)
        halo_x = (self.width() - halo_w) // 2
        self._halo.setGeometry(halo_x, 0, halo_w, self.height())

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), qc("bg_window"))
        # Bottom separator line.
        pen = QPen(qc("border"))
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


def _gear_icon(size: int = 22) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(qc("text_secondary"))
    pen.setWidth(2)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    center = size / 2
    inner = size * 0.18
    outer_a = size * 0.34
    outer_b = size * 0.46
    painter.drawEllipse(
        int(center - inner),
        int(center - inner),
        int(inner * 2),
        int(inner * 2),
    )
    for i in range(8):
        angle = tau * i / 8
        x1 = center + cos(angle) * outer_a
        y1 = center + sin(angle) * outer_a
        x2 = center + cos(angle) * outer_b
        y2 = center + sin(angle) * outer_b
        painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    painter.end()
    return QIcon(pixmap)


def _header_button_qss(primary: bool) -> str:
    border = c("info") if primary else c("border_strong")
    text = c("info") if primary else c("text_primary")
    return f"""
        QPushButton {{
            background-color: {c('bg_panel')};
            color: {text};
            border: 1px solid {border};
            border-radius: 0px;
            font-family: {FONT_CHROME_FAMILIES};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            padding: 8px 18px;
        }}
        QPushButton:hover {{
            background-color: {c('bg_panel_hover')};
            border-color: {c('info')};
            color: {c('info')};
        }}
        QPushButton:pressed {{
            background-color: {c('bg_window')};
        }}
    """


def _header_cog_qss() -> str:
    return f"""
        QPushButton {{
            background-color: {c('bg_panel')};
            color: {c('text_primary')};
            border: 1px solid {c('border_strong')};
            border-radius: 0px;
            font-size: 16px;
        }}
        QPushButton:hover {{
            border-color: {c('info')};
            color: {c('info')};
        }}
    """


# ---------------------------------------------------------------------------
# Old TelemetryHeader — kept for other tabs that still import it.
# Recolored to use mint/info tokens; behavior unchanged.
# ---------------------------------------------------------------------------


class TelemetryHeader(QFrame):
    """Hard-edged section header used by diagnostic tool tabs."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        module: str,
        state: str = "READY",
        accent: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        accent = accent or c("mint")
        self.setObjectName("telemetry-header")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QFrame#telemetry-header {{
                background-color: {c('bg_panel')};
                border: 1px solid {c('border')};
                border-left: 3px solid {accent};
                border-radius: 0;
            }}
            QLabel#telemetry-title {{
                color: {c('text_primary')};
                font-family: {FONT_CHROME_FAMILIES};
                font-size: 20px;
                font-weight: 600;
            }}
            QLabel#telemetry-subtitle {{
                color: {c('info')};
                font-family: {FONT_CHROME_FAMILIES};
                font-size: 11px;
                letter-spacing: 1.5px;
            }}
            QLabel#telemetry-meta {{
                color: {accent};
                font-family: {FONT_MONO_FAMILIES};
                font-size: 10px;
                font-weight: 600;
                padding: 6px 10px;
                border: 1px solid {c('border')};
                background-color: {c('bg_panel_inner')};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName("telemetry-title")
        copy.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("telemetry-subtitle")
        subtitle_label.setWordWrap(True)
        copy.addWidget(subtitle_label)
        layout.addLayout(copy, 1)

        meta = QLabel(f"MODULE  {module}\nSTATE   {state}")
        meta.setObjectName("telemetry-meta")
        meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(meta)


# ---------------------------------------------------------------------------
# MetricCard — hero number + sub-row, inside a BracketedPanel.
# ---------------------------------------------------------------------------


class MetricCard(BracketedPanel):
    """A metric card with a title, hero number, optional sparkline, and sub-row.

    Backwards-compatible signature: ``MetricCard(title)`` and
    ``card.set_value(text, detail, status)`` still work for existing callers,
    but new layouts can use ``set_hero``/``set_sub_columns``/``push_sample``
    for richer rendering.
    """

    STATUS_TOKEN = {
        "healthy": "mint",
        "neutral": "text_primary",
        "warning": "warn",
        "error": "error",
    }

    def __init__(
        self,
        title: str,
        sub_columns: tuple[str, ...] = ("RTT", "LOGS"),
        sparkline: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(title=title, parent=parent)
        self.setMinimumHeight(124)
        self.setMaximumHeight(145)

        layout = self.layout()
        layout.setContentsMargins(14, 30, 14, 0)
        layout.setSpacing(0)

        # Vertical breathing space above the hero so it sits below the title.
        layout.addStretch(1)

        # Hero row
        self._hero = QLabel("--")
        self._hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_font = mono_font(38, QFont.Weight.Light)
        self._hero.setFont(hero_font)
        self._hero.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 40px; font-weight: 300;"
        )
        layout.addWidget(self._hero)

        # Optional sparkline trail
        self._spark: Optional[Sparkline] = None
        if sparkline:
            layout.addItem(QSpacerItem(0, 6, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
            self._spark = Sparkline(capacity=30, height=14)
            layout.addWidget(self._spark)

        layout.addStretch(1)

        # Sub-row: pairs of (label, value) spread evenly across the panel.
        self._sub_columns = sub_columns
        self._sub_values: list[QLabel] = []
        sub_frame = QFrame()
        sub_frame.setObjectName("metric-subframe")
        sub_frame.setStyleSheet(
            f"QFrame#metric-subframe {{"
            f"  background: transparent;"
            f"  border-top: 1px solid {c('border')};"
            f"}}"
        )
        sub_row = QHBoxLayout(sub_frame)
        sub_row.setContentsMargins(2, 8, 2, 10)
        sub_row.setSpacing(8)
        for idx, name in enumerate(sub_columns):
            if idx > 0:
                separator = QFrame()
                separator.setObjectName("metric-subseparator")
                separator.setFixedWidth(1)
                separator.setStyleSheet(
                    f"QFrame#metric-subseparator {{"
                    f"  background-color: {c('border_faint')};"
                    f"  border: none;"
                    f"}}"
                )
                sub_row.addWidget(separator)

            col = QVBoxLayout()
            col.setSpacing(2)
            col.setContentsMargins(0, 0, 0, 0)
            label = QLabel(name.upper())
            label.setStyleSheet(
                f"color: {c('info_dim')}; "
                f"font-family: {FONT_CHROME_FAMILIES}; "
                "font-size: 10px; font-weight: 600; letter-spacing: 1.8px;"
            )
            col.addWidget(label)

            value = QLabel("--")
            value.setStyleSheet(
                f"color: {c('mint')}; "
                f"font-family: {FONT_MONO_FAMILIES}; "
                "font-size: 13px; font-weight: 500;"
            )
            self._sub_values.append(value)
            col.addWidget(value)
            sub_row.addLayout(col, 1)
        layout.addWidget(sub_frame)

    # ------------------------------------------------------------------ API
    def set_hero(self, text: str, status: str = "neutral") -> None:
        self._hero.setText(text)
        size = 27 if len(text) > 15 else (31 if len(text) > 11 else 36)
        self._hero.setFont(mono_font(size, QFont.Weight.Light))
        token = self.STATUS_TOKEN.get(status, "text_primary")
        self._hero.setStyleSheet(
            f"color: {c(token)}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            f"font-size: {size}px; font-weight: 300;"
        )

    def set_sub(self, idx: int, value: str, status: str = "healthy") -> None:
        if 0 <= idx < len(self._sub_values):
            token = self.STATUS_TOKEN.get(status, "mint")
            label = self._sub_values[idx]
            label.setText(value)
            label.setStyleSheet(
                f"color: {c(token)}; "
                f"font-family: {FONT_MONO_FAMILIES}; "
                "font-size: 12px; font-weight: 500;"
            )

    def push_sample(self, value: Optional[float]) -> None:
        if self._spark is not None:
            self._spark.push(value)

    # ----------------------------- Legacy compatibility ------------------
    def set_value(self, value: str, detail: str = "", status: str = "neutral") -> None:
        """Legacy single-line update. Splits *detail* on ``|`` to fill sub columns."""
        self.set_hero(value, status)
        if detail:
            parts = [p.strip() for p in detail.split("|")]
            for i, part in enumerate(parts):
                self.set_sub(i, part, status if status != "neutral" else "healthy")


# ---------------------------------------------------------------------------
# StatusBanner — used inside the StatusPanel.
# ---------------------------------------------------------------------------


class StatusBanner(QFrame):
    """Compact HEALTH banner with a coloured outline and pulsing live dot."""

    LEVELS = {
        "healthy":  ("mint",  "HEALTH: MONITORING", "Network is stable"),
        "warning":  ("warn",  "HEALTH: WARN",       "Anomalies detected"),
        "error":    ("error", "HEALTH: ALERT",      "Connectivity issue"),
        "unknown":  ("text_secondary", "HEALTH: STANDBY",  "Collecting data"),
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("status-banner")
        self.setMinimumHeight(86)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._headline = QLabel("HEALTH: MONITORING")
        self._headline.setStyleSheet(
            f"color: {c('mint')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 13px; font-weight: 700; letter-spacing: 1.5px;"
        )
        layout.addWidget(self._headline)

        self._explanation = QLabel("Network is stable")
        self._explanation.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        self._explanation.setWordWrap(True)
        layout.addWidget(self._explanation)

        # Bottom row: "Monitoring..." + uptime + live dot
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 4, 0, 0)
        bottom.setSpacing(6)

        self._uptime_label = QLabel("Monitoring…")
        self._uptime_label.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 10px;"
        )
        bottom.addWidget(self._uptime_label)
        bottom.addStretch()

        self._uptime_value = QLabel("00:00:00")
        self._uptime_value.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        bottom.addWidget(self._uptime_value)

        self._dot = LiveDot("mint", 8)
        bottom.addWidget(self._dot)

        layout.addLayout(bottom)

        self._level = "healthy"
        self._apply_level()

    def update_status(self, summary: str, explanation: str, category: str):
        level_map = {
            "healthy": "healthy",
            "lan_issue": "error",
            "isp_wan_issue": "error",
            "dns_issue": "warning",
            "upstream_route_issue": "warning",
            "intermittent": "warning",
            "unknown": "unknown",
        }
        level = level_map.get(category, "unknown")
        self._level = level
        _token, default_head, _default_sub = self.LEVELS[level]
        # Headline stays anchored to the level so the panel reads as a
        # status indicator, not a rolling log. The diagnosis copy goes to
        # the subtitle.
        self._headline.setText(default_head)
        self._explanation.setText(summary or explanation or _default_sub)
        self._apply_level()

    def set_uptime(self, text: str) -> None:
        self._uptime_value.setText(text)

    def _apply_level(self) -> None:
        token, _, _ = self.LEVELS[self._level]
        accent = c(token)
        self._headline.setStyleSheet(
            f"color: {accent}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 13px; font-weight: 700; letter-spacing: 1.5px;"
        )
        self._dot.set_color(token)
        # Transparent inside, mint outline so the dashboard texture flows
        # behind the banner and only the border reads as a frame.
        self.setStyleSheet(
            f"QFrame#status-banner {{"
            f"  background: transparent;"
            f"  border: 1px solid {accent};"
            f"}}"
        )


# ---------------------------------------------------------------------------
# KeyValueRow — used inside Targets / System panels.
# ---------------------------------------------------------------------------


class KeyValueRow(QWidget):
    """One-line row: key on the left, mono value on the right, optional dot."""

    def __init__(
        self,
        key: str,
        value: str = "—",
        with_dot: bool = False,
        dot_token: str = "mint",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)

        self._key = QLabel(key)
        self._key.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        layout.addWidget(self._key)
        layout.addStretch()

        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"color: {c('text_primary')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        layout.addWidget(self._value)

        self._dot: Optional[LiveDot] = None
        if with_dot:
            self._dot = LiveDot(dot_token, 7)
            layout.addWidget(self._dot)

    def set_value(self, text: str) -> None:
        self._value.setText(text)

    def set_dot(self, token: str) -> None:
        if self._dot is not None:
            self._dot.set_color(token)


# ---------------------------------------------------------------------------
# MonitorStatusBar — bottom strip with monitoring stats.
# ---------------------------------------------------------------------------


def _footer_separator() -> QFrame:
    line = QFrame()
    line.setFixedWidth(1)
    line.setFixedHeight(22)
    line.setStyleSheet(
        f"QFrame {{ background-color: {c('border_faint')}; border: none; }}"
    )
    return line


class MonitorStatusBar(QFrame):
    """The footer status strip styled like the reference."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("monitor-statusbar")
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"QFrame#monitor-statusbar {{"
            f"  background-color: {c('bg_window')};"
            f"  border-top: 1px solid {c('border')};"
            f"}}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 4, 18, 4)
        row.setSpacing(14)

        # Left cluster
        self._mon_label = QLabel("Monitoring:")
        self._mon_label.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_CHROME_FAMILIES}; "
            "font-size: 11px;"
        )
        row.addWidget(self._mon_label)

        self._mon_value = QLabel("ON")
        self._mon_value.setStyleSheet(
            f"color: {c('mint')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px; font-weight: 600;"
        )
        row.addWidget(self._mon_value)

        self._mon_dot = LiveDot("mint", 7)
        row.addWidget(self._mon_dot)

        row.addWidget(_footer_separator())

        self._items: dict[str, QLabel] = {}
        for key, default in [
            ("interval", "Interval: --"),
            ("targets", "Targets: --"),
            ("duration", "Duration: Continuous"),
            ("threads", "Threads: --"),
        ]:
            label = QLabel(default)
            label.setStyleSheet(
                f"color: {c('text_secondary')}; "
                f"font-family: {FONT_CHROME_FAMILIES}; "
                "font-size: 11px;"
            )
            row.addWidget(label)
            self._items[key] = label
            if key in {"targets", "threads"}:
                row.addWidget(_footer_separator())

        row.addStretch()

        # Right cluster: countdown + DB + version
        self._countdown = QLabel("")
        self._countdown.setStyleSheet(
            f"color: {c('info')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        row.addWidget(self._countdown)

        self._db_label = QLabel("DB: history.db")
        self._db_label.setStyleSheet(
            f"color: {c('text_secondary')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        row.addWidget(self._db_label)
        row.addWidget(_footer_separator())

        self._version_label = QLabel("v1.1.0")
        self._version_label.setStyleSheet(
            f"color: {c('text_dim')}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px;"
        )
        row.addWidget(self._version_label)

    def set_monitoring(self, on: bool) -> None:
        self._mon_value.setText("ON" if on else "PAUSED")
        token = "mint" if on else "warn"
        self._mon_value.setStyleSheet(
            f"color: {c(token)}; "
            f"font-family: {FONT_MONO_FAMILIES}; "
            "font-size: 11px; font-weight: 600;"
        )
        self._mon_dot.set_color(token)

    def set_interval(self, seconds: float) -> None:
        self._items["interval"].setText(f"Interval: {seconds:.1f}s")

    def set_targets(self, count: int) -> None:
        self._items["targets"].setText(f"Targets: {count}")

    def set_threads(self, count: int) -> None:
        self._items["threads"].setText(f"Threads: {count}")

    def set_countdown(self, seconds: int) -> None:
        if seconds > 0:
            self._countdown.setText(f"Next check in {seconds}s")
        else:
            self._countdown.setText("")

    def set_status_text(self, text: str) -> None:
        # Tucked into the monitoring label slot to surface short messages.
        if text:
            self._mon_label.setText(text)
        else:
            self._mon_label.setText("Monitoring:")


# ---------------------------------------------------------------------------
# Backwards-compat alias
# ---------------------------------------------------------------------------

# main_window.py still imports BrandHeader from this module today; alias so
# the old name keeps working until the import site is updated.
BrandHeader = LosshoundHeader

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from losshound.gui.branding import losshound_pixmap


class BrandHeader(QFrame):
    """Top-level product rail with the app mark and live context."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("brand-header")
        self.setStyleSheet("""
            QFrame#brand-header {
                background-color: #101318;
                border-bottom: 1px solid #333b47;
            }
            QLabel#brand-title {
                color: #e6edf6;
                font-size: 15px;
                font-weight: 800;
            }
            QLabel#brand-subtitle {
                color: #788596;
                font-size: 11px;
            }
            QLabel#brand-chip {
                background-color: #151b22;
                border: 1px solid #3a4350;
                color: #89b8c5;
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 10px;
                padding: 4px 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(losshound_pixmap(32))
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mark)

        text_stack = QVBoxLayout()
        text_stack.setContentsMargins(0, 0, 0, 0)
        text_stack.setSpacing(0)

        title = QLabel("LOSSHOUND")
        title.setObjectName("brand-title")
        text_stack.addWidget(title)

        subtitle = QLabel("Network diagnosis")
        subtitle.setObjectName("brand-subtitle")
        text_stack.addWidget(subtitle)
        layout.addLayout(text_stack)

        layout.addStretch()

        for label in ("LOCAL", "WINDOWS", "LIVE MONITOR"):
            chip = QLabel(label)
            chip.setObjectName("brand-chip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(chip)


class TelemetryHeader(QFrame):
    """Hard-edged section header used by diagnostic tool tabs."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        module: str,
        state: str = "READY",
        accent: str = "#62c7d8",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("telemetry-header")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QFrame#telemetry-header {{
                background-color: #111820;
                border: 1px solid #315469;
                border-left: 4px solid {accent};
                border-radius: 0;
            }}
            QLabel#telemetry-title {{
                color: #e6edf6;
                font-size: 21px;
                font-weight: 800;
            }}
            QLabel#telemetry-subtitle {{
                color: #89b8c5;
                font-size: 12px;
            }}
            QLabel#telemetry-meta {{
                color: {accent};
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 10px;
                font-weight: 700;
                padding: 4px 8px;
                border: 1px solid #3a4350;
                background-color: #151b22;
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


class MetricCard(QFrame):
    """A compact card displaying a labeled metric value with status color."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "metric-card")
        self.setMinimumHeight(76)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)

        self._title_label = QLabel(title.upper())
        self._title_label.setStyleSheet(
            "font-size: 10px; color: #788596; font-weight: bold; "
            "letter-spacing: 1px;"
        )
        layout.addWidget(self._title_label)

        self._value_label = QLabel("--")
        self._value_label.setStyleSheet(
            "font-family: 'Cascadia Mono', 'Consolas', monospace; "
            "font-size: 21px; font-weight: bold; color: #d8dee9;"
        )
        layout.addWidget(self._value_label)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet("font-size: 11px; color: #8f9aaa;")
        layout.addWidget(self._detail_label)

    def set_value(self, value: str, detail: str = "", status: str = "neutral"):
        self._value_label.setText(value)
        self._detail_label.setText(detail)

        colors = {
            "healthy": "#75c884",
            "warning": "#d9b65f",
            "error": "#e06363",
            "neutral": "#d8dee9",
        }
        color = colors.get(status, "#d8dee9")
        self._value_label.setStyleSheet(
            "font-family: 'Cascadia Mono', 'Consolas', monospace; "
            f"font-size: 21px; font-weight: bold; color: {color};"
        )


class StatusBanner(QFrame):
    """Large status banner showing current diagnosis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._status_label = QLabel("Initializing...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #788596;"
        )
        layout.addWidget(self._status_label)

        self._explanation_label = QLabel("")
        self._explanation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._explanation_label.setWordWrap(True)
        self._explanation_label.setStyleSheet("font-size: 12px; color: #8f9aaa;")
        layout.addWidget(self._explanation_label)

        self._set_style("unknown")

    def update_status(self, summary: str, explanation: str, category: str):
        self._status_label.setText(summary)
        self._explanation_label.setText(explanation)

        style_map = {
            "healthy": "healthy",
            "lan_issue": "error",
            "isp_wan_issue": "error",
            "dns_issue": "warning",
            "upstream_route_issue": "warning",
            "intermittent": "warning",
            "unknown": "unknown",
        }
        self._set_style(style_map.get(category, "unknown"))

    def _set_style(self, level: str):
        styles = {
            "healthy": {
                "bg": "#16261d", "border": "#315a3c",
                "text": "#75c884", "sub": "#8fcf9a",
            },
            "warning": {
                "bg": "#2b2518", "border": "#6d5623",
                "text": "#d9b65f", "sub": "#c6aa68",
            },
            "error": {
                "bg": "#2d1b1d", "border": "#73353a",
                "text": "#e06363", "sub": "#cf7777",
            },
            "unknown": {
                "bg": "#1b2028", "border": "#3a4350",
                "text": "#788596", "sub": "#677383",
            },
        }
        s = styles.get(level, styles["unknown"])
        self.setStyleSheet(f"""
            StatusBanner {{
                background-color: {s['bg']};
                border: 1px solid {s['border']};
                border-left: 4px solid {s['text']};
                border-radius: 0px;
            }}
        """)
        self._status_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {s['text']};"
        )
        self._explanation_label.setStyleSheet(
            f"font-size: 12px; color: {s['sub']};"
        )

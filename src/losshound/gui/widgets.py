from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class MetricCard(QFrame):
    """A compact card displaying a labeled metric value with status color."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "metric-card")
        self.setStyleSheet("""
            MetricCard {
                background-color: #2a2a3d;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self._title_label = QLabel(title.upper())
        self._title_label.setStyleSheet("font-size: 10px; color: #6c7086; font-weight: bold;")
        layout.addWidget(self._title_label)

        self._value_label = QLabel("--")
        self._value_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(self._value_label)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        layout.addWidget(self._detail_label)

    def set_value(self, value: str, detail: str = "", status: str = "neutral"):
        self._value_label.setText(value)
        self._detail_label.setText(detail)

        colors = {
            "healthy": "#a6e3a1",
            "warning": "#f9e2af",
            "error": "#f38ba8",
            "neutral": "#cdd6f4",
        }
        color = colors.get(status, "#cdd6f4")
        self._value_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {color};"
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
            "font-size: 18px; font-weight: bold; color: #6c7086;"
        )
        layout.addWidget(self._status_label)

        self._explanation_label = QLabel("")
        self._explanation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._explanation_label.setWordWrap(True)
        self._explanation_label.setStyleSheet("font-size: 12px; color: #a6adc8;")
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
                "bg": "#1e3a2f", "border": "#2d5a45",
                "text": "#a6e3a1", "sub": "#7ec9a0",
            },
            "warning": {
                "bg": "#3a351e", "border": "#5a4d2d",
                "text": "#f9e2af", "sub": "#d4c08a",
            },
            "error": {
                "bg": "#3a1e2e", "border": "#5a2d45",
                "text": "#f38ba8", "sub": "#d07090",
            },
            "unknown": {
                "bg": "#2a2a3d", "border": "#45475a",
                "text": "#6c7086", "sub": "#585b70",
            },
        }
        s = styles.get(level, styles["unknown"])
        self.setStyleSheet(f"""
            StatusBanner {{
                background-color: {s['bg']};
                border: 1px solid {s['border']};
                border-radius: 8px;
            }}
        """)
        self._status_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {s['text']};"
        )
        self._explanation_label.setStyleSheet(
            f"font-size: 12px; color: {s['sub']};"
        )

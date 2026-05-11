def button_style(kind: str = "default") -> str:
    variants = {
        "default": ("#252b35", "#454f5d", "#e6edf6", "#2f3743"),
        "primary": ("#1d343e", "#62c7d8", "#e6edf6", "#263f49"),
        "success": ("#1c3325", "#75c884", "#e6edf6", "#25432f"),
        "warning": ("#3a301d", "#d9b65f", "#f3e3b4", "#493b20"),
        "danger": ("#3a2024", "#e06363", "#f0d7d7", "#4a252a"),
    }
    bg, border, text, hover = variants.get(kind, variants["default"])
    return f"""
    QPushButton {{
        background-color: {bg};
        color: {text};
        border: 1px solid {border};
        border-left: 3px solid {border};
        border-radius: 0;
        font-weight: 700;
        padding: 10px 18px;
    }}
    QPushButton:hover {{
        background-color: {hover};
        border-color: #89b8c5;
        border-left-color: {border};
    }}
    QPushButton:pressed {{
        background-color: #15171d;
        padding-top: 11px;
        padding-bottom: 9px;
    }}
    QPushButton:disabled {{
        background-color: #1a1f27;
        color: #596474;
        border-color: #303844;
        border-left-color: #303844;
    }}
    """


def get_dark_stylesheet() -> str:
    return """
    QWidget {
        background-color: #15171d;
        color: #d8dee9;
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 13px;
    }

    QMainWindow {
        background-color: #15171d;
    }

    QTabWidget::pane {
        border: 1px solid #333b47;
        border-radius: 0;
        background-color: #15171d;
    }

    QTabBar::tab {
        background-color: #1d222b;
        color: #8f9aaa;
        padding: 10px 20px;
        margin-right: 1px;
        border: 1px solid #333b47;
        border-bottom: none;
        border-radius: 0;
        font-weight: 650;
    }

    QTabBar::tab:selected {
        background-color: #111820;
        color: #e6edf6;
        border-top: 3px solid #62c7d8;
    }

    QTabBar::tab:hover {
        background-color: #2a313d;
        color: #e6edf6;
    }

    QFrame.metric-card {
        background-color: #1b2028;
        border: 1px solid #3a4350;
        border-radius: 2px;
        padding: 12px;
    }

    QLabel {
        background: transparent;
    }

    QLabel.title {
        font-size: 11px;
        color: #788596;
        font-weight: bold;
        text-transform: uppercase;
    }

    QLabel.value {
        font-size: 20px;
        font-weight: bold;
    }

    QLabel.value-healthy {
        font-size: 20px;
        font-weight: bold;
        color: #75c884;
    }

    QLabel.value-warning {
        font-size: 20px;
        font-weight: bold;
        color: #d9b65f;
    }

    QLabel.value-error {
        font-size: 20px;
        font-weight: bold;
        color: #e06363;
    }

    QLabel.status-banner-healthy {
        background-color: #16261d;
        color: #75c884;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 2px;
        border: 1px solid #315a3c;
    }

    QLabel.status-banner-warning {
        background-color: #2b2518;
        color: #d9b65f;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 2px;
        border: 1px solid #6d5623;
    }

    QLabel.status-banner-error {
        background-color: #2d1b1d;
        color: #e06363;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 2px;
        border: 1px solid #73353a;
    }

    QLabel.status-banner-unknown {
        background-color: #1b2028;
        color: #788596;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 2px;
        border: 1px solid #3a4350;
    }

    QPushButton {
        background-color: #252b35;
        color: #e6edf6;
        border: 1px solid #454f5d;
        padding: 8px 16px;
        border-radius: 2px;
        font-weight: bold;
    }

    QPushButton:hover {
        background-color: #2f3743;
        border-color: #62c7d8;
    }

    QPushButton:pressed {
        background-color: #1b2028;
    }

    QPushButton:disabled {
        background-color: #1a1f27;
        color: #596474;
        border-color: #303844;
    }

    QPushButton.primary {
        background-color: #1d343e;
        color: #e6edf6;
        border-color: #62c7d8;
        border-radius: 0;
    }

    QPushButton.primary:hover {
        background-color: #263f49;
    }

    QTableWidget {
        background-color: #181c23;
        border: 1px solid #333b47;
        border-radius: 0;
        gridline-color: #2d3540;
        selection-background-color: #263542;
        selection-color: #e6edf6;
    }

    QTableWidget::item {
        padding: 3px 8px;
    }

    QHeaderView::section {
        background-color: #232934;
        color: #b8c4d6;
        padding: 6px 8px;
        border: none;
        border-right: 1px solid #333b47;
        font-weight: bold;
    }

    QTextEdit {
        background-color: #181c23;
        border: 1px solid #333b47;
        border-radius: 0;
        padding: 8px;
        font-family: "Cascadia Mono", "Cascadia Code", "Consolas", monospace;
        font-size: 12px;
    }

    QScrollBar:vertical {
        background-color: #15171d;
        width: 10px;
    }

    QScrollBar::handle:vertical {
        background-color: #3a4350;
        border-radius: 0;
        min-height: 20px;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        background-color: #15171d;
        height: 10px;
    }

    QScrollBar::handle:horizontal {
        background-color: #3a4350;
        border-radius: 0;
        min-width: 20px;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }

    QSpinBox, QDoubleSpinBox, QLineEdit {
        background-color: #1d222b;
        color: #e6edf6;
        border: 1px solid #3a4350;
        border-radius: 2px;
        padding: 4px 8px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
        border-color: #62c7d8;
    }

    QGroupBox {
        border: 1px solid #333b47;
        border-radius: 0;
        margin-top: 12px;
        padding-top: 16px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        padding: 0 8px;
        color: #62c7d8;
    }

    QStatusBar {
        background-color: #101318;
        color: #788596;
        border-top: 1px solid #333b47;
    }

    QComboBox {
        background-color: #1d222b;
        color: #e6edf6;
        border: 1px solid #3a4350;
        border-radius: 2px;
        padding: 4px 8px;
    }

    QComboBox::drop-down {
        border: none;
    }

    QComboBox QAbstractItemView {
        background-color: #1d222b;
        color: #e6edf6;
        selection-background-color: #263542;
    }
    """

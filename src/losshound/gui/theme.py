def button_style(kind: str = "default") -> str:
    variants = {
        "default": ("#131720", "#242f42", "#e6edf6", "#1c222e"),
        "primary": ("#1d343e", "#62c7d8", "#e6edf6", "#264855"),
        "success": ("#1c3325", "#75c884", "#e6edf6", "#264a35"),
        "warning": ("#3a301d", "#d9b65f", "#f3e3b4", "#524426"),
        "danger": ("#3a2024", "#e06363", "#f0d7d7", "#522a30"),
    }
    bg, border, text, hover = variants.get(kind, variants["default"])
    return f"""
    QPushButton {{
        background-color: {bg};
        color: {text};
        border: 1px solid {border};
        border-radius: 6px;
        font-weight: bold;
        padding: 8px 16px;
    }}
    QPushButton:hover {{
        background-color: {hover};
        border-color: #62c7d8;
    }}
    QPushButton:pressed {{
        background-color: #0d0f13;
    }}
    QPushButton:disabled {{
        background-color: #0f1217;
        color: #4f5a69;
        border-color: #1a202a;
    }}
    """


def get_dark_stylesheet() -> str:
    return """
    QWidget {
        background-color: #0d0f13;
        color: #cdd6f4;
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 13px;
    }

    QMainWindow {
        background-color: #0d0f13;
    }

    QTabWidget::pane {
        border: 1px solid #1a2230;
        border-radius: 6px;
        background-color: #0d0f13;
    }

    QTabBar::tab {
        background-color: #131720;
        color: #8f9aaa;
        padding: 8px 18px;
        margin: 4px 2px;
        border: 1px solid #242f42;
        border-radius: 6px;
        font-weight: bold;
    }

    QTabBar::tab:selected {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a2d37, stop:1 #13222b);
        color: #62c7d8;
        border-color: #62c7d8;
    }

    QTabBar::tab:hover {
        background-color: #1c222e;
        color: #e6edf6;
    }

    QFrame.metric-card {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141822, stop:1 #0d1016);
        border: 1px solid #20293a;
        border-radius: 8px;
        padding: 12px;
    }

    QFrame.metric-card:hover {
        border-color: #62c7d8;
    }

    QLabel {
        background: transparent;
    }

    QLabel.title {
        font-size: 11px;
        color: #788596;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    QLabel.value {
        font-size: 20px;
        font-weight: bold;
        color: #cdd6f4;
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
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0c1a11, stop:1 #132e1d);
        color: #75c884;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #225c34;
    }

    QLabel.status-banner-warning {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #221a0b, stop:1 #3a2b13);
        color: #d9b65f;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #6d521d;
    }

    QLabel.status-banner-error {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a0f12, stop:1 #42161b);
        color: #e06363;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #7c2227;
    }

    QLabel.status-banner-unknown {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #131720, stop:1 #1f2735);
        color: #788596;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #2b3648;
    }

    QPushButton {
        background-color: #131720;
        color: #e6edf6;
        border: 1px solid #242f42;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: bold;
    }

    QPushButton:hover {
        background-color: #1c222e;
        border-color: #62c7d8;
    }

    QPushButton:pressed {
        background-color: #0d0f13;
    }

    QPushButton:disabled {
        background-color: #0f1217;
        color: #4f5a69;
        border-color: #1a202a;
    }

    QPushButton.primary {
        background-color: #1d343e;
        color: #e6edf6;
        border-color: #62c7d8;
        border-radius: 6px;
    }

    QPushButton.primary:hover {
        background-color: #264855;
    }

    QTableWidget {
        background-color: #10141c;
        border: 1px solid #1a2230;
        border-radius: 6px;
        gridline-color: #18202d;
        selection-background-color: #1a2d3e;
        selection-color: #e6edf6;
    }

    QTableWidget::item {
        padding: 6px 10px;
    }

    QTableWidget QComboBox {
        background-color: #131720;
        color: #e6edf6;
        border: 1px solid #242f42;
        border-radius: 4px;
        padding: 2px 6px;
        margin: 2px;
    }

    QTableWidget QLineEdit {
        background-color: #131720;
        color: #e6edf6;
        border: 1px solid #242f42;
        border-radius: 4px;
        padding: 2px 6px;
        margin: 2px;
    }

    QHeaderView::section {
        background-color: #171d27;
        color: #9aa8bd;
        padding: 8px 10px;
        border: none;
        border-bottom: 2px solid #242f42;
        border-right: 1px solid #1a2230;
        font-weight: bold;
    }

    QHeaderView:vertical {
        qproperty-defaultSectionSize: 36;
    }

    QTextEdit {
        background-color: #10141c;
        border: 1px solid #1a2230;
        border-radius: 6px;
        padding: 8px;
        font-family: "Cascadia Mono", "Cascadia Code", "Consolas", monospace;
        font-size: 12px;
    }

    QScrollBar:vertical {
        background-color: transparent;
        width: 8px;
        margin: 0px;
    }

    QScrollBar::handle:vertical {
        background-color: #242f42;
        border-radius: 4px;
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background-color: #62c7d8;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        background-color: transparent;
        height: 8px;
        margin: 0px;
    }

    QScrollBar::handle:horizontal {
        background-color: #242f42;
        border-radius: 4px;
        min-width: 20px;
    }

    QScrollBar::handle:horizontal:hover {
        background-color: #62c7d8;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }

    QSpinBox, QDoubleSpinBox, QLineEdit {
        background-color: #131720;
        color: #e6edf6;
        border: 1px solid #242f42;
        border-radius: 6px;
        padding: 6px 10px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
        border-color: #62c7d8;
    }

    QGroupBox {
        border: 1px solid #1a2230;
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 20px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 15px;
        padding: 0 5px;
        color: #62c7d8;
    }

    QStatusBar {
        background-color: #0a0b0e;
        color: #788596;
        border-top: 1px solid #1a2230;
    }

    QComboBox {
        background-color: #131720;
        color: #e6edf6;
        border: 1px solid #242f42;
        border-radius: 6px;
        padding: 6px 10px;
    }

    QComboBox::drop-down {
        border: none;
    }

    QComboBox QAbstractItemView {
        background-color: #131720;
        color: #e6edf6;
        selection-background-color: #1a2d3e;
    }
    """

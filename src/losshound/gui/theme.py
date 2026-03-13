def get_dark_stylesheet() -> str:
    return """
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }

    QMainWindow {
        background-color: #1e1e2e;
    }

    QTabWidget::pane {
        border: 1px solid #45475a;
        border-radius: 4px;
        background-color: #1e1e2e;
    }

    QTabBar::tab {
        background-color: #313244;
        color: #a6adc8;
        padding: 8px 20px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }

    QTabBar::tab:selected {
        background-color: #45475a;
        color: #cdd6f4;
    }

    QTabBar::tab:hover {
        background-color: #585b70;
    }

    QFrame.metric-card {
        background-color: #2a2a3d;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 12px;
    }

    QLabel {
        background: transparent;
    }

    QLabel.title {
        font-size: 11px;
        color: #6c7086;
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
        color: #a6e3a1;
    }

    QLabel.value-warning {
        font-size: 20px;
        font-weight: bold;
        color: #f9e2af;
    }

    QLabel.value-error {
        font-size: 20px;
        font-weight: bold;
        color: #f38ba8;
    }

    QLabel.status-banner-healthy {
        background-color: #1e3a2f;
        color: #a6e3a1;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #2d5a45;
    }

    QLabel.status-banner-warning {
        background-color: #3a351e;
        color: #f9e2af;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #5a4d2d;
    }

    QLabel.status-banner-error {
        background-color: #3a1e2e;
        color: #f38ba8;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #5a2d45;
    }

    QLabel.status-banner-unknown {
        background-color: #2a2a3d;
        color: #6c7086;
        font-size: 18px;
        font-weight: bold;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #45475a;
    }

    QPushButton {
        background-color: #45475a;
        color: #cdd6f4;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
    }

    QPushButton:hover {
        background-color: #585b70;
    }

    QPushButton:pressed {
        background-color: #313244;
    }

    QPushButton.primary {
        background-color: #89b4fa;
        color: #1e1e2e;
    }

    QPushButton.primary:hover {
        background-color: #74c7ec;
    }

    QTableWidget {
        background-color: #2a2a3d;
        border: 1px solid #45475a;
        border-radius: 4px;
        gridline-color: #313244;
        selection-background-color: #45475a;
    }

    QTableWidget::item {
        padding: 4px 8px;
    }

    QHeaderView::section {
        background-color: #313244;
        color: #a6adc8;
        padding: 6px 8px;
        border: none;
        border-right: 1px solid #45475a;
        font-weight: bold;
    }

    QTextEdit {
        background-color: #2a2a3d;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 8px;
        font-family: "Cascadia Code", "Consolas", monospace;
        font-size: 12px;
    }

    QScrollBar:vertical {
        background-color: #1e1e2e;
        width: 10px;
    }

    QScrollBar::handle:vertical {
        background-color: #45475a;
        border-radius: 5px;
        min-height: 20px;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        background-color: #1e1e2e;
        height: 10px;
    }

    QScrollBar::handle:horizontal {
        background-color: #45475a;
        border-radius: 5px;
        min-width: 20px;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }

    QSpinBox, QDoubleSpinBox, QLineEdit {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
        border-color: #89b4fa;
    }

    QGroupBox {
        border: 1px solid #45475a;
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 16px;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        padding: 0 8px;
        color: #89b4fa;
    }

    QStatusBar {
        background-color: #181825;
        color: #6c7086;
        border-top: 1px solid #313244;
    }

    QComboBox {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QComboBox::drop-down {
        border: none;
    }

    QComboBox QAbstractItemView {
        background-color: #313244;
        color: #cdd6f4;
        selection-background-color: #45475a;
    }
    """

"""QoS (Quality of Service) management tab — per-app network priority rules."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from losshound.gui.theme import button_style
from losshound.core.qos import (
    PRESET_DESCRIPTIONS, PRIORITY_PRESETS,
    QosResult, QosRule,
    apply_rule, check_admin, load_saved_rules, remove_all_losshound_policies,
    remove_rule, save_rules,
)


class _ApplyWorker(QObject):
    finished = Signal(object)  # QosResult

    def __init__(self, rule: QosRule):
        super().__init__()
        self._rule = rule

    def run(self):
        result = apply_rule(self._rule)
        self.finished.emit(result)


class _RemoveWorker(QObject):
    finished = Signal(object)

    def __init__(self, rule_name: str):
        super().__init__()
        self._name = rule_name

    def run(self):
        result = remove_rule(self._name)
        self.finished.emit(result)


class _RemoveAllWorker(QObject):
    finished = Signal(object)

    def run(self):
        results = remove_all_losshound_policies()
        self.finished.emit(results)


class QosTab(QWidget):
    def shutdown(self):
        from losshound.gui._shutdown import stop_qthreads
        stop_qthreads(getattr(self, "_threads", []))

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules: list[QosRule] = load_saved_rules()
        self._threads: list[QThread] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QLabel("Per-App Network Priority (QoS)")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #d8dee9;")
        layout.addWidget(header)

        admin_note = QLabel(
            "Requires Administrator privileges. "
            "Rules use DSCP markings to prioritize traffic at the OS level."
        )
        admin_note.setStyleSheet("color: #788596; font-size: 11px;")
        admin_note.setWordWrap(True)
        layout.addWidget(admin_note)

        # Add rule row
        add_row = QHBoxLayout()

        self._app_input = QLineEdit()
        self._app_input.setPlaceholderText("App name or path (e.g. chrome.exe)")
        self._app_input.setMinimumWidth(200)
        add_row.addWidget(self._app_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_app)
        add_row.addWidget(browse_btn)

        self._priority_combo = QComboBox()
        for preset in PRIORITY_PRESETS:
            self._priority_combo.addItem(preset)
        self._priority_combo.setCurrentText("High")
        self._priority_combo.currentTextChanged.connect(self._update_desc)
        add_row.addWidget(self._priority_combo)

        add_btn = QPushButton("Add Rule")
        add_btn.setStyleSheet(button_style("success"))
        add_btn.clicked.connect(self._add_rule)
        add_row.addWidget(add_btn)

        layout.addLayout(add_row)

        # Preset description
        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet("color: #788596; font-size: 11px; padding-left: 4px;")
        layout.addWidget(self._desc_label)
        self._update_desc(self._priority_combo.currentText())

        # Rules table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            "Application", "Priority", "DSCP", "Status", "Actions",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in range(1, 5):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        # Bottom buttons
        bottom = QHBoxLayout()

        apply_all_btn = QPushButton("Apply All Rules")
        apply_all_btn.setStyleSheet(button_style("primary"))
        apply_all_btn.clicked.connect(self._apply_all)
        bottom.addWidget(apply_all_btn)

        remove_all_btn = QPushButton("Remove All Policies")
        remove_all_btn.setStyleSheet(button_style("danger"))
        remove_all_btn.clicked.connect(self._remove_all)
        bottom.addWidget(remove_all_btn)

        bottom.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #788596;")
        bottom.addWidget(self._status_label)

        layout.addLayout(bottom)

        # Populate table
        self._refresh_table()

    def _update_desc(self, preset: str):
        desc = PRESET_DESCRIPTIONS.get(preset, "")
        dscp = PRIORITY_PRESETS.get(preset, 0)
        self._desc_label.setText(f"DSCP {dscp} — {desc}")

    def _browse_app(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Application",
            "C:/Program Files",
            "Executables (*.exe);;All Files (*)",
        )
        if path:
            self._app_input.setText(path)

    def _add_rule(self):
        app_path = self._app_input.text().strip()
        if not app_path:
            self._status_label.setText("Enter an app name or browse for an .exe first")
            self._status_label.setStyleSheet("color: #d9b65f;")
            return

        preset = self._priority_combo.currentText()
        dscp = PRIORITY_PRESETS[preset]
        name = Path(app_path).stem if "\\" in app_path or "/" in app_path else app_path.replace(".exe", "")

        # Check for duplicate
        for r in self._rules:
            if r.name == name:
                self._status_label.setText(f"Rule for '{name}' already exists")
                return

        rule = QosRule(
            name=name,
            app_path=app_path,
            priority_preset=preset,
            dscp_value=dscp,
        )
        self._rules.append(rule)
        save_rules(self._rules)
        self._refresh_table()
        self._app_input.clear()
        self._status_label.setText(f"Added rule for {name}")

    def _refresh_table(self):
        self._table.setRowCount(0)
        for i, rule in enumerate(self._rules):
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, QTableWidgetItem(rule.app_path))
            self._table.setItem(row, 1, QTableWidgetItem(rule.priority_preset))
            self._table.setItem(row, 2, QTableWidgetItem(str(rule.dscp_value)))

            status_item = QTableWidgetItem("Saved" if rule.active else "Disabled")
            self._table.setItem(row, 3, status_item)

            # Action buttons
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 2, 4, 2)

            apply_btn = QPushButton("Apply")
            apply_btn.setFixedWidth(60)
            apply_btn.clicked.connect(lambda checked, r=rule: self._apply_single(r))
            actions_layout.addWidget(apply_btn)

            del_btn = QPushButton("Delete")
            del_btn.setFixedWidth(60)
            del_btn.setStyleSheet("color: #e06363;")
            del_btn.clicked.connect(lambda checked, r=rule: self._delete_rule(r))
            actions_layout.addWidget(del_btn)

            self._table.setCellWidget(row, 4, actions)

    def _apply_single(self, rule: QosRule):
        self._status_label.setText(f"Applying {rule.name}...")
        thread = QThread()
        worker = _ApplyWorker(rule)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda res: self._on_apply_done(res, thread))
        thread.start()
        self._threads.append(thread)

    def _on_apply_done(self, result: QosResult, thread: QThread):
        thread.quit()
        thread.wait(3000)
        if thread in self._threads:
            self._threads.remove(thread)

        if result.success:
            self._status_label.setText(f"{result.rule_name}: {result.action}")
            self._status_label.setStyleSheet("color: #75c884;")
        else:
            self._status_label.setText(f"{result.rule_name}: {result.message[:60]}")
            self._status_label.setStyleSheet("color: #e06363;")

    def _delete_rule(self, rule: QosRule):
        self._rules = [r for r in self._rules if r.name != rule.name]
        save_rules(self._rules)
        self._refresh_table()
        self._status_label.setText(f"Deleted saved rule: {rule.name}; removing policy...")
        self._status_label.setStyleSheet("color: #788596;")

        thread = QThread()
        worker = _RemoveWorker(rule.name)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda res, name=rule.name: self._on_delete_policy_done(res, thread, name)
        )
        thread.start()
        self._threads.append(thread)

    def _on_delete_policy_done(self, result: QosResult, thread: QThread, name: str):
        thread.quit()
        thread.wait(3000)
        if thread in self._threads:
            self._threads.remove(thread)

        if result.success:
            self._status_label.setText(f"Removed Windows policy: {name}")
            self._status_label.setStyleSheet("color: #75c884;")
        else:
            self._status_label.setText(
                f"Saved rule deleted. Policy removal skipped/failed: {result.message[:70]}"
            )
            self._status_label.setStyleSheet("color: #d9b65f;")

    def _apply_all(self):
        if not self._rules:
            self._status_label.setText("No rules to apply")
            return
        self._status_label.setText("Applying all rules...")
        for rule in self._rules:
            if rule.active:
                self._apply_single(rule)

    def _remove_all(self):
        reply = QMessageBox.question(
            self, "Remove All QoS Policies",
            "Remove all Losshound QoS policies from Windows?\n"
            "(Saved rules will be kept.)",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._status_label.setText("Removing Losshound QoS policies...")
        self._status_label.setStyleSheet("color: #d9b65f;")

        thread = QThread()
        worker = _RemoveAllWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda res: self._on_remove_all_done(res, thread))
        thread.start()
        self._threads.append(thread)

    def _on_remove_all_done(self, results: list[QosResult], thread: QThread):
        thread.quit()
        thread.wait(3000)
        if thread in self._threads:
            self._threads.remove(thread)

        removed = sum(1 for r in results if r.success)
        self._status_label.setText(f"Removed {removed} policies")
        self._status_label.setStyleSheet("color: #d9b65f;")

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dashboard_qos_offer_emits_requested_app(qapp):
    from losshound.gui.dashboard import DashboardTab

    dashboard = DashboardTab()
    requested: list[str] = []
    dashboard.qos_apply_requested.connect(requested.append)

    dashboard.show_qos_offer("steam.exe", "local traffic 10 down / 2 up Mbps")
    dashboard.qos_mitigation_panel._apply_button.click()

    assert requested == ["steam.exe"]
    assert not dashboard.qos_mitigation_panel.isHidden()


def test_qos_tab_lag_mitigation_saves_and_applies(qapp, monkeypatch):
    import losshound.gui.qos_tab as qos_tab

    saved_snapshots = []
    monkeypatch.setattr(qos_tab, "load_saved_rules", lambda: [])
    monkeypatch.setattr(
        qos_tab,
        "save_rules",
        lambda rules: saved_snapshots.append(list(rules)),
    )

    tab = qos_tab.QosTab()
    applied = []
    monkeypatch.setattr(tab, "_apply_single", lambda rule: applied.append(rule))

    rule = tab.apply_lag_mitigation("steam.exe")

    assert rule.name == "LagMitigation_steam"
    assert rule.priority_preset == "Bulk"
    assert saved_snapshots[-1] == [rule]
    assert applied == [rule]

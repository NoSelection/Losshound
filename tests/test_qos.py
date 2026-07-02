from unittest.mock import MagicMock, patch

from losshound.core.qos import (
    PRIORITY_PRESETS,
    QosRule,
    _run,
    apply_rule,
    build_lag_mitigation_rule,
    remove_rule,
)


def test_qos_runner_uses_interruptible_subprocess():
    with patch(
        "losshound.core.qos.run_subprocess_interruptible",
        return_value=("out", "err", 7),
    ) as mock_run:
        result = _run(["powershell", "-NoProfile"], timeout=3)

    mock_run.assert_called_once_with(["powershell", "-NoProfile"], 3)
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.returncode == 7


def test_build_lag_mitigation_rule_defaults_to_bulk_priority():
    rule = build_lag_mitigation_rule("C:\\Program Files\\Steam\\steam.exe")

    assert rule.name == "LagMitigation_steam"
    assert rule.app_path == "steam.exe"
    assert rule.priority_preset == "Bulk"
    assert rule.dscp_value == PRIORITY_PRESETS["Bulk"]
    assert "lag attribution" in rule.note


def test_build_lag_mitigation_rule_bounds_long_rule_names():
    rule = build_lag_mitigation_rule("x" * 100 + ".exe")
    assert len(rule.name) <= 64


def test_apply_rule_without_admin_returns_actionable_failure():
    rule = QosRule(
        name="LagMitigation_steam",
        app_path="steam.exe",
        priority_preset="Bulk",
        dscp_value=PRIORITY_PRESETS["Bulk"],
    )

    with patch("losshound.core.qos.check_admin", return_value=False):
        result = apply_rule(rule)

    assert result.success is False
    assert result.action == "failed"
    assert "Administrator privileges required" in result.message


def test_qos_validation():
    # Test valid rule name and app path
    rule_valid = QosRule(
        name="Game_Rule",
        app_path="C:\\games\\game.exe",
        priority_preset="Realtime",
        dscp_value=46
    )
    
    with patch("losshound.core.qos.check_admin", return_value=True), \
         patch("losshound.core.qos._run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        # Test valid rule application
        res = apply_rule(rule_valid)
        assert res.success is True
        assert res.action == "created"
        
        # Test invalid rule name (command injection attempt)
        rule_invalid_name = QosRule(
            name="Game'; Start-Process calc; '",
            app_path="C:\\games\\game.exe",
            priority_preset="Realtime",
            dscp_value=46
        )
        res = apply_rule(rule_invalid_name)
        assert res.success is False
        assert "Invalid rule name" in res.message
        
        # Test invalid app path (command injection attempt)
        rule_invalid_path = QosRule(
            name="GameRule",
            app_path="game.exe'; Start-Process calc; '",
            priority_preset="Realtime",
            dscp_value=46
        )
        res = apply_rule(rule_invalid_path)
        assert res.success is False
        assert "Invalid application path" in res.message

        # Test remove rule validation
        res = remove_rule("Game_Rule")
        assert res.success is True
        
        res_invalid = remove_rule("Game'; Start-Process calc; '")
        assert res_invalid.success is False
        assert "Invalid rule name" in res_invalid.message

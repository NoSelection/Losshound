from unittest.mock import patch, MagicMock
from losshound.core.qos import QosRule, apply_rule, remove_rule

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

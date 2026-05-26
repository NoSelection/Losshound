"""Tests for the LAN-discovery firewall rule manager.

These tests mock the PowerShell subprocess so we can verify the right commands
are issued without ever touching the real Windows Firewall on the test host.
"""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from losshound.core import firewall


def _make_completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def test_skips_when_not_admin():
    with patch.object(firewall, "_is_running_as_admin", return_value=False), \
         patch("subprocess.run") as run_mock:
        result = firewall.ensure_lan_discovery_firewall_rules()
    assert result is False
    assert run_mock.call_count == 0


@pytest.mark.skipif(sys.platform != "win32", reason="firewall logic only runs on Windows")
def test_skips_when_not_windows():
    with patch.object(firewall.sys, "platform", "linux"):
        result = firewall.ensure_lan_discovery_firewall_rules()
    assert result is False


def test_creates_rule_when_missing():
    """When no rule exists, a single New-NetFirewallRule call should be made."""
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=r"C:\app\losshound.exe"), \
         patch("subprocess.run") as run_mock:
        run_mock.side_effect = [
            _make_completed(0, stdout=""),                # check returns nothing
            _make_completed(0, stdout="ok"),              # create succeeds
        ]
        result = firewall.ensure_lan_discovery_firewall_rules()

    assert result is True
    assert run_mock.call_count == 2
    create_script = run_mock.call_args_list[1].args[0][-1]
    # Must be scoped to the right exe, not "all of Python"
    assert r"C:\app\losshound.exe" in create_script
    # Specific UDP ports, no overly broad allow-all
    assert "5353,5355,1900,137" in create_script
    assert "-Protocol UDP" in create_script
    assert "-Direction Inbound" in create_script
    assert "-Action Allow" in create_script


def test_noop_when_rule_already_matches():
    """If the rule already targets the same exe, no Remove or New call is issued."""
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=r"C:\app\losshound.exe"), \
         patch("subprocess.run") as run_mock:
        run_mock.side_effect = [
            _make_completed(0, stdout=r"C:\app\losshound.exe"),
        ]
        result = firewall.ensure_lan_discovery_firewall_rules()

    assert result is True
    # Exactly one call: the check. No remove, no create.
    assert run_mock.call_count == 1


def test_replaces_rule_when_program_path_changed():
    """If a rule exists for a different exe path, remove the old one and create fresh."""
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=r"C:\NEW\losshound.exe"), \
         patch("subprocess.run") as run_mock:
        run_mock.side_effect = [
            _make_completed(0, stdout=r"C:\OLD\losshound.exe"),  # stale path
            _make_completed(0, stdout=""),                       # remove
            _make_completed(0, stdout="ok"),                     # create
        ]
        result = firewall.ensure_lan_discovery_firewall_rules()

    assert result is True
    assert run_mock.call_count == 3
    remove_script = run_mock.call_args_list[1].args[0][-1]
    create_script = run_mock.call_args_list[2].args[0][-1]
    assert "Remove-NetFirewallRule" in remove_script
    assert r"C:\NEW\losshound.exe" in create_script
    assert r"C:\OLD\losshound.exe" not in create_script


def test_returns_false_when_powershell_create_fails():
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=r"C:\app\losshound.exe"), \
         patch("subprocess.run") as run_mock:
        run_mock.side_effect = [
            _make_completed(0, stdout=""),
            _make_completed(1, stderr="Access denied"),
        ]
        result = firewall.ensure_lan_discovery_firewall_rules()

    assert result is False


def test_handles_powershell_timeout_gracefully():
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=r"C:\app\losshound.exe"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=15)):
        result = firewall.ensure_lan_discovery_firewall_rules()
    assert result is False


def test_remove_skips_when_not_admin():
    with patch.object(firewall, "_is_running_as_admin", return_value=False), \
         patch("subprocess.run") as run_mock:
        result = firewall.remove_lan_discovery_firewall_rules()
    assert result is False
    assert run_mock.call_count == 0


def test_remove_calls_remove_netfirewallrule():
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch("subprocess.run") as run_mock:
        run_mock.return_value = _make_completed(0)
        result = firewall.remove_lan_discovery_firewall_rules()
    assert result is True
    assert run_mock.call_count == 1
    script = run_mock.call_args.args[0][-1]
    assert "Remove-NetFirewallRule" in script
    assert "Losshound-LAN-Discovery-UDP" in script
    # Must use SilentlyContinue so absence isn't an error
    assert "SilentlyContinue" in script


def test_remove_returns_false_when_powershell_errors():
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch("subprocess.run") as run_mock:
        run_mock.return_value = _make_completed(1, stderr="boom")
        result = firewall.remove_lan_discovery_firewall_rules()
    assert result is False


def test_apply_preference_enabled_calls_ensure():
    with patch.object(firewall, "ensure_lan_discovery_firewall_rules", return_value=True) as ensure, \
         patch.object(firewall, "remove_lan_discovery_firewall_rules", return_value=True) as remove:
        result = firewall.apply_firewall_preference(True)
    assert result is True
    ensure.assert_called_once()
    remove.assert_not_called()


def test_apply_preference_disabled_calls_remove():
    with patch.object(firewall, "ensure_lan_discovery_firewall_rules", return_value=True) as ensure, \
         patch.object(firewall, "remove_lan_discovery_firewall_rules", return_value=True) as remove:
        result = firewall.apply_firewall_preference(False)
    assert result is True
    remove.assert_called_once()
    ensure.assert_not_called()


def test_escapes_single_quotes_in_path():
    """An exe path containing a single quote must be escaped, not break the PowerShell command."""
    tricky_path = r"C:\Mom's Files\losshound.exe"
    with patch.object(firewall, "_is_running_as_admin", return_value=True), \
         patch.object(firewall.sys, "platform", "win32"), \
         patch.object(firewall, "_current_executable", return_value=tricky_path), \
         patch("subprocess.run") as run_mock:
        run_mock.side_effect = [
            _make_completed(0, stdout=""),
            _make_completed(0, stdout="ok"),
        ]
        result = firewall.ensure_lan_discovery_firewall_rules()
    assert result is True
    create_script = run_mock.call_args_list[1].args[0][-1]
    # PowerShell escape: ' becomes ''
    assert r"C:\Mom''s Files\losshound.exe" in create_script

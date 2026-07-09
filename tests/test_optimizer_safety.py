from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from losshound.core.optimizer import (
    BackupData,
    DnsState,
    NetworkOptimizer,
    TcpSettings,
    _make_result,
)


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_make_result_rejects_unchanged_wrong_readback():
    result = _make_result(
        name="TCP auto-tuning",
        success=True,
        before="disabled",
        after="disabled",
        desired="normal",
        needs_admin=True,
        verification="Post-apply read: disabled",
    )

    assert not result.success
    assert result.status == "Failed"
    assert "expected Normal" in result.error
    assert result.after == "Disabled"


@patch("losshound.core.optimizer._run", return_value=_proc())
@patch("losshound.core.optimizer.NetworkOptimizer.get_tcp_settings")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_optimize_tcp_requires_observed_desired_state(
    _mock_admin, mock_get_tcp_settings, _mock_run,
):
    initial = TcpSettings(
        auto_tuning_level="disabled",
        congestion_provider="cubic",
        ecn_capability="enabled",
        rss="enabled",
        dca="enabled",
        timestamps="enabled",
    )
    unchanged_wrong = TcpSettings(
        auto_tuning_level="disabled",
        congestion_provider="cubic",
        ecn_capability="enabled",
        rss="enabled",
        dca="enabled",
        timestamps="enabled",
    )
    desired = TcpSettings(
        auto_tuning_level="normal",
        congestion_provider="cubic",
        ecn_capability="enabled",
        rss="enabled",
        dca="enabled",
        timestamps="enabled",
    )
    mock_get_tcp_settings.side_effect = [
        initial, unchanged_wrong, desired, desired, desired, desired, desired,
    ]

    results = NetworkOptimizer().optimize_tcp()

    auto_tuning = next(r for r in results if r.name == "TCP auto-tuning")
    assert not auto_tuning.success
    assert auto_tuning.status == "Failed"
    assert "expected normal, observed disabled" in auto_tuning.error
    assert all(r.success for r in results if r.name != "TCP auto-tuning")


@patch("losshound.core.optimizer._run")
def test_dns_read_fallback_is_scoped_to_requested_adapter(mock_run):
    mock_run.side_effect = [
        _proc(returncode=1, stderr="PowerShell unavailable"),
        _proc(
            stdout=(
                'Configuration for interface "Ethernet"\n'
                "Statically Configured DNS Servers: 1.1.1.1\n"
                "                                    8.8.8.8\n"
            ),
        ),
    ]

    state = NetworkOptimizer()._get_dns_state("Ethernet")

    assert state == DnsState(
        "Ethernet", ("1.1.1.1", "8.8.8.8"), False, True,
    )
    fallback_command = mock_run.call_args_list[1].args[0]
    assert "name=Ethernet" in fallback_command


@patch("losshound.core.optimizer._run")
@patch("losshound.core.dns_bench.query_dns_server", return_value=1.0)
@patch(
    "losshound.core.optimizer.NetworkOptimizer._active_adapter_name",
    return_value="Ethernet",
)
@patch("losshound.core.optimizer.NetworkOptimizer._get_dns_state")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_dns_secondary_command_failure_rolls_back_exact_state(
    _mock_admin,
    mock_get_dns_state,
    _mock_adapter,
    _mock_query,
    mock_run,
):
    original = DnsState(
        "Ethernet", ("1.1.1.1", "8.8.8.8"), False, True,
    )
    partial = DnsState("Ethernet", ("9.9.9.9",), False, True)
    mock_get_dns_state.side_effect = [original, partial, original]
    mock_run.side_effect = [
        _proc(),
        _proc(returncode=1, stderr="secondary failed"),
        _proc(),
        _proc(),
    ]

    result = NetworkOptimizer().apply_dns("9.9.9.9", "149.112.112.112")

    assert not result.success
    assert result.status == "Failed"
    assert "rollback succeeded" in result.error
    assert "restored and verified" in result.note
    assert len(mock_run.call_args_list) == 4
    for call in mock_run.call_args_list:
        assert "name=Ethernet" in call.args[0]


@patch("losshound.core.optimizer._run")
@patch("losshound.core.dns_bench.query_dns_server", return_value=1.0)
@patch(
    "losshound.core.optimizer.NetworkOptimizer._active_adapter_name",
    return_value="Ethernet",
)
@patch("losshound.core.optimizer.NetworkOptimizer._get_dns_state")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_dns_success_requires_primary_and_secondary_readback(
    _mock_admin,
    mock_get_dns_state,
    _mock_adapter,
    _mock_query,
    mock_run,
):
    original = DnsState(
        "Ethernet", ("1.1.1.1", "8.8.8.8"), False, True,
    )
    missing_secondary = DnsState("Ethernet", ("9.9.9.9",), False, True)
    mock_get_dns_state.side_effect = [original, missing_secondary, original]
    mock_run.return_value = _proc()

    result = NetworkOptimizer().apply_dns("9.9.9.9", "149.112.112.112")

    assert not result.success
    assert "DNS verification failed" in result.error
    assert "rollback succeeded" in result.error


@patch("losshound.core.optimizer._run", return_value=_proc())
@patch("losshound.core.optimizer.NetworkOptimizer._get_dns_state")
@patch("losshound.core.optimizer.NetworkOptimizer._active_adapter_name")
@patch("losshound.core.optimizer.NetworkOptimizer.apply_mtu")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_restore_dns_uses_backed_up_adapter_not_current_active(
    _mock_admin,
    mock_apply_mtu,
    mock_active_adapter,
    mock_get_dns_state,
    mock_run,
):
    mock_active_adapter.return_value = "Wi-Fi"
    mock_apply_mtu.return_value = _make_result(
        name="Restore MTU", success=True,
        before="1400", after="1500", desired="1500",
        needs_admin=True, verification="Post-apply MTU read: 1500",
    )
    before = DnsState("Ethernet", ("9.9.9.9",), False, True)
    restored = DnsState(
        "Ethernet", ("1.1.1.1", "8.8.8.8"), False, True,
    )
    mock_get_dns_state.side_effect = [before, restored]
    backup = BackupData(
        timestamp="2026-07-09T00:00:00+00:00",
        tcp_settings=TcpSettings(),
        dns_servers=("1.1.1.1", "8.8.8.8"),
        mtu=1500,
        network_throttling=None,
        nagle_disabled=False,
        dns_adapter_name="Ethernet",
        dns_automatic=False,
        dns_server_list=("1.1.1.1", "8.8.8.8"),
    )

    results = NetworkOptimizer().restore_backup(backup)

    dns_result = next(r for r in results if r.name == "Restore DNS")
    assert dns_result.success
    mock_active_adapter.assert_not_called()
    assert len(mock_run.call_args_list) == 2
    assert all(
        "name=Ethernet" in call.args[0] for call in mock_run.call_args_list
    )


@patch("losshound.core.optimizer._run", return_value=_proc())
@patch("losshound.core.optimizer.NetworkOptimizer._get_dns_state")
@patch("losshound.core.optimizer.NetworkOptimizer.apply_mtu")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_restore_dns_preserves_automatic_mode(
    _mock_admin, mock_apply_mtu, mock_get_dns_state, mock_run,
):
    mock_apply_mtu.return_value = _make_result(
        name="Restore MTU", success=True,
        before="1400", after="1500", desired="1500",
        needs_admin=True, verification="Post-apply MTU read: 1500",
    )
    mock_get_dns_state.side_effect = [
        DnsState("Ethernet", ("9.9.9.9",), False, True),
        DnsState("Ethernet", ("192.168.1.1",), True, True),
    ]
    backup = BackupData(
        timestamp="2026-07-09T00:00:00+00:00",
        tcp_settings=TcpSettings(),
        dns_servers=("192.168.1.1", ""),
        mtu=1500,
        network_throttling=None,
        nagle_disabled=False,
        dns_adapter_name="Ethernet",
        dns_automatic=True,
        dns_server_list=("192.168.1.1",),
    )

    results = NetworkOptimizer().restore_backup(backup)

    dns_result = next(r for r in results if r.name == "Restore DNS")
    assert dns_result.success
    command = mock_run.call_args.args[0]
    assert "source=dhcp" in command
    assert not any(part.startswith("address=") for part in command)


@patch("losshound.core.optimizer._read_registry_dword_snapshot")
@patch("winreg.DeleteValue")
@patch("winreg.OpenKey")
@patch("losshound.core.optimizer.NetworkOptimizer.apply_mtu")
@patch(
    "losshound.core.optimizer.NetworkOptimizer.check_admin",
    return_value=True,
)
def test_restore_deletes_only_values_known_absent_in_backup(
    _mock_admin,
    mock_apply_mtu,
    _mock_open_key,
    mock_delete_value,
    mock_registry_snapshot,
):
    mock_apply_mtu.return_value = _make_result(
        name="Restore MTU", success=True,
        before="1400", after="1500", desired="1500",
        needs_admin=True, verification="Post-apply MTU read: 1500",
    )
    mock_registry_snapshot.side_effect = [
        (True, 0xFFFFFFFF), (False, None),
        (True, 1500), (False, None),
        (True, 10), (False, None),
    ]
    backup = BackupData(
        timestamp="2026-07-09T00:00:00+00:00",
        tcp_settings=TcpSettings(),
        dns_servers=("", ""),
        mtu=1500,
        network_throttling=None,
        nagle_disabled=False,
        network_throttling_present=False,
        fast_send_datagram_threshold_present=False,
        system_responsiveness_present=False,
    )

    results = NetworkOptimizer().restore_backup(backup)

    deleted_names = {call.args[1] for call in mock_delete_value.call_args_list}
    assert deleted_names == {
        "NetworkThrottlingIndex",
        "FastSendDatagramThreshold",
        "SystemResponsiveness",
    }
    registry_results = [r for r in results if r.name.startswith("Restore ")]
    assert all(r.success for r in registry_results)


def test_restore_retains_retry_backup_when_step_is_unsupported(tmp_path):
    import losshound.core.optimizer as optimizer_module

    backup_file = tmp_path / "optimizer_backup.json"
    backup_file.write_text("{}", encoding="utf-8")
    backup = BackupData(
        timestamp="2026-07-09T00:00:00+00:00",
        tcp_settings=TcpSettings(),
        dns_servers=("", ""),
        mtu=1500,
        network_throttling=None,
        nagle_disabled=False,
        network_throttling_present=False,
        fast_send_datagram_threshold_present=False,
        system_responsiveness_present=False,
    )
    unsupported_mtu = _make_result(
        name="Restore MTU", success=False,
        before="current", after="", needs_admin=True,
        error="MTU restore unsupported on this adapter",
    )

    with patch.object(optimizer_module, "_BACKUP_FILE", backup_file), \
            patch.object(NetworkOptimizer, "_load_backup", return_value=backup), \
            patch.object(NetworkOptimizer, "check_admin", return_value=True), \
            patch.object(NetworkOptimizer, "apply_mtu", return_value=unsupported_mtu), \
            patch.object(
                optimizer_module,
                "_read_registry_dword_snapshot",
                return_value=(False, None),
            ), \
            patch("winreg.OpenKey"), \
            patch("winreg.DeleteValue"):
        results = NetworkOptimizer().restore_backup()

    assert any(result.status == "Unsupported" for result in results)
    assert backup_file.is_file()

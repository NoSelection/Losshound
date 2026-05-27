import sys
import unittest
from unittest.mock import MagicMock, patch
import winreg

from losshound.core.optimizer import NetworkOptimizer, BackupData, TcpSettings, AdapterBackup
from losshound.core.models import PingResult

class TestOptimizerExtensions(unittest.TestCase):

    @patch("losshound.core.optimizer._run")
    def test_get_tcp_heuristics(self, mock_run):
        mock_run.return_value.stdout = (
            "TCP Window Scaling heuristics Parameters\n"
            "----------------------------------------------\n"
            "Window Scaling heuristics         : disabled \n"
        )
        opt = NetworkOptimizer()
        val = opt.get_tcp_heuristics()
        self.assertEqual(val, "disabled")

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_tcp_heuristics")
    @patch("losshound.core.optimizer._run")
    def test_disable_tcp_heuristics(self, mock_run, mock_get_heuristics, mock_check_admin):
        mock_check_admin.return_value = True
        mock_get_heuristics.side_effect = ["enabled", "disabled"]
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        opt = NetworkOptimizer()
        res = opt.disable_tcp_heuristics()
        self.assertTrue(res.success)
        self.assertEqual(res.before, "Enabled")  # normalized
        self.assertEqual(res.after, "Disabled")

    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    def test_get_system_responsiveness(self, mock_query, mock_open):
        mock_query.return_value = (10, winreg.REG_DWORD)
        opt = NetworkOptimizer()
        val = opt.get_system_responsiveness()
        self.assertEqual(val, 10)

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_system_responsiveness")
    @patch("winreg.OpenKey")
    @patch("winreg.SetValueEx")
    def test_apply_system_responsiveness(self, mock_set_val, mock_open_key, mock_get_resp, mock_check_admin):
        mock_check_admin.return_value = True
        mock_get_resp.side_effect = [20, 10]

        opt = NetworkOptimizer()
        res = opt.apply_system_responsiveness(10)
        self.assertTrue(res.success)
        self.assertEqual(res.before, "20")
        self.assertEqual(res.after, "10")

    @patch("losshound.core.optimizer._run")
    def test_find_optimal_mtu_skips_inconclusive_probes(self, mock_run):
        mock_run.return_value.stdout = "Request timed out."

        opt = NetworkOptimizer()

        self.assertIsNone(opt.find_optimal_mtu())

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_system_responsiveness")
    @patch("losshound.core.optimizer.NetworkOptimizer.apply_system_responsiveness")
    @patch("losshound.core.ping.ping")
    def test_benchmark_optimal_responsiveness(self, mock_ping, mock_apply_resp, mock_get_resp, mock_check_admin):
        mock_check_admin.return_value = True
        mock_get_resp.return_value = 20

        # Mock ping replies for candidates 20, 10, 0
        # Score = RTT + 2 * Jitter
        # Candidate 20: RTT=15, Jitter=5 -> Score = 25
        # Candidate 10: RTT=10, Jitter=1 -> Score = 12
        # Candidate 0: RTT=12, Jitter=3 -> Score = 18
        # Winner should be 10.
        res_20 = PingResult(target="8.8.8.8", timestamp=None, packets_sent=10, packets_received=10, loss_percent=0.0, rtt_avg=15.0, rtt_jitter=5.0)
        res_10 = PingResult(target="8.8.8.8", timestamp=None, packets_sent=10, packets_received=10, loss_percent=0.0, rtt_avg=10.0, rtt_jitter=1.0)
        res_0 = PingResult(target="8.8.8.8", timestamp=None, packets_sent=10, packets_received=10, loss_percent=0.0, rtt_avg=12.0, rtt_jitter=3.0)

        # Mock ping calls: warmup, then benchmark pings
        mock_ping.side_effect = [
            res_20, res_20,  # candidate 20
            res_10, res_10,  # candidate 10
            res_0, res_0     # candidate 0
        ]

        opt = NetworkOptimizer()
        best, stats = opt.benchmark_optimal_responsiveness(target="8.8.8.8")
        self.assertEqual(best, 10)
        self.assertEqual(stats[20], (15.0, 5.0))
        self.assertEqual(stats[10], (10.0, 1.0))
        self.assertEqual(stats[0], (12.0, 3.0))

    @patch("losshound.core.optimizer.NetworkOptimizer._save_backup")
    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_tcp_settings")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_current_dns")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_current_mtu")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_network_throttling_index")
    @patch("losshound.core.optimizer.NetworkOptimizer._backup_adapter_settings")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_tcp_heuristics")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_system_responsiveness")
    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    @patch("winreg.EnumKey")
    def test_backup_and_load(self, mock_enum, mock_query, mock_open_key, mock_get_resp, mock_get_heuristics, mock_backup_adapter, mock_get_throttling, mock_get_mtu, mock_get_dns, mock_get_tcp, mock_check_admin, mock_save):
        mock_check_admin.return_value = True
        mock_get_tcp.return_value = TcpSettings()
        mock_get_dns.return_value = ("1.1.1.1", "8.8.8.8")
        mock_get_mtu.return_value = 1500
        mock_get_throttling.return_value = 10
        mock_backup_adapter.return_value = AdapterBackup("Ethernet", True, True, False, False, "0")
        mock_get_heuristics.return_value = "disabled"
        mock_get_resp.return_value = 10
        mock_enum.side_effect = ["mock-guid-123", OSError()]
        mock_query.side_effect = [
            (["192.168.1.1"], winreg.REG_SZ),  # DhcpDefaultGateway
            (1, winreg.REG_DWORD),             # TCPNoDelay
            (0, winreg.REG_DWORD),             # TcpDelAckTicks
            (1024, winreg.REG_DWORD),          # FastSendDatagramThreshold
        ]

        opt = NetworkOptimizer()
        backup = opt.create_backup()

        self.assertEqual(backup.tcp_heuristics, "disabled")
        self.assertEqual(backup.system_responsiveness, 10)
        self.assertEqual(backup.tcp_del_ack_ticks, 0)
        self.assertEqual(backup.fast_send_datagram_threshold, 1024)
        self.assertEqual(backup.adapter.eee_enabled, "0")

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_active_adapter")
    @patch("losshound.core.optimizer._run")
    def test_optimize_eee(self, mock_run, mock_get_adapter, mock_check_admin):
        mock_check_admin.return_value = True
        mock_get_adapter.return_value = MagicMock(name="Ethernet")
        mock_get_adapter.return_value.name = "Ethernet"

        # Mock EEE check
        # First call: get EEE keyword. Second call: get EEE current value. Third call: set EEE value. Fourth call: verify EEE value.
        proc1 = MagicMock()
        proc1.stdout = "*EEE"
        proc2 = MagicMock()
        proc2.stdout = "1"
        proc3 = MagicMock()
        proc3.returncode = 0
        proc4 = MagicMock()
        proc4.stdout = "0"
        mock_run.side_effect = [proc1, proc2, proc3, proc4]

        opt = NetworkOptimizer()
        res = opt.optimize_eee(disable=True)
        self.assertTrue(res.success)
        self.assertEqual(res.before, "Enabled")
        self.assertEqual(res.after, "Disabled")

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.get_active_adapter")
    @patch("losshound.core.optimizer._run")
    def test_optimize_rsc(self, mock_run, mock_get_adapter, mock_check_admin):
        mock_check_admin.return_value = True
        mock_get_adapter.return_value = MagicMock(name="Ethernet")
        mock_get_adapter.return_value.name = "Ethernet"

        # Mock RSC check
        # First call: check support. Second call: disable RSC. Third call: verify.
        proc1 = MagicMock()
        proc1.stdout = "True"
        proc2 = MagicMock()
        proc2.returncode = 0
        proc3 = MagicMock()
        proc3.stdout = "False"
        mock_run.side_effect = [proc1, proc2, proc3]

        opt = NetworkOptimizer()
        res = opt.optimize_rsc(disable=True)
        self.assertTrue(res.success)
        self.assertEqual(res.before, "Enabled")
        self.assertEqual(res.after, "Disabled")

    def test_make_result_status_derivation(self):
        from losshound.core.optimizer import _make_result

        # 1. Test reboot_required bypass when already optimal
        res = _make_result(
            name="Test", success=True, before="1500", after="1500", desired="1500",
            reboot_required=True, note="reboot recommended", needs_admin=True
        )
        self.assertEqual(res.status, "Verified")
        self.assertEqual(res.note, "Already optimized (set to 1500)")

        # 2. Test reboot_required active when not optimal
        res = _make_result(
            name="Test", success=True, before="1400", after="1500", desired="1500",
            reboot_required=True, note="reboot recommended", needs_admin=True
        )
        self.assertEqual(res.status, "Reboot required")
        self.assertEqual(res.note, "reboot recommended")

        # 3. Test unsupported adapter property errors
        res = _make_result(
            name="Test", success=False, before="--", after="--",
            error="Adapter does not support RSC", needs_admin=True
        )
        self.assertEqual(res.status, "Unsupported")

    @patch("losshound.core.optimizer.NetworkOptimizer.check_admin")
    @patch("losshound.core.optimizer.NetworkOptimizer.create_backup")
    @patch("losshound.core.optimizer.NetworkOptimizer.optimize_winsock_datagram_threshold")
    @patch("losshound.core.optimizer.NetworkOptimizer.disable_tcp_heuristics")
    @patch("losshound.core.optimizer.NetworkOptimizer.apply_system_responsiveness")
    @patch("losshound.core.optimizer.NetworkOptimizer.optimize_nagle")
    @patch("losshound.core.optimizer.NetworkOptimizer.optimize_tcp")
    @patch("losshound.core.optimizer.NetworkOptimizer.optimize_adapter")
    @patch("losshound.core.optimizer.NetworkOptimizer.disable_network_throttling")
    def test_optimize_report_summary_formatting(self, mock_throttling, mock_adapter, mock_tcp, mock_nagle, mock_resp, mock_heur, mock_afd, mock_backup, mock_check_admin):
        from losshound.core.optimizer import _make_result, NetworkOptimizer, BackupData, TcpSettings
        mock_check_admin.return_value = True
        mock_backup.return_value = BackupData("", TcpSettings(), ("", ""), 1500, 10, True)
        
        # Setup mocks to return specific status results
        mock_afd.return_value = _make_result(name="AFD", success=True, before="0", after="1", needs_admin=True, reboot_required=True) # Reboot
        mock_heur.return_value = _make_result(name="Heuristics", success=False, before="--", after="--", needs_admin=True, error="requires administrator privileges") # Skipped admin
        mock_resp.return_value = _make_result(name="Responsiveness", success=False, before="--", after="--", needs_admin=True, error="skipped by choice") # Skipped other
        mock_nagle.return_value = _make_result(name="Nagle", success=True, before="normal", after="normal", desired="normal", needs_admin=True) # Verified
        
        # Return lists of dummy results for tcp and adapter
        dummy = _make_result(name="Dummy", success=True, before="1", after="1", desired="1", needs_admin=True)
        mock_tcp.return_value = [dummy]
        mock_adapter.return_value = [dummy]
        mock_throttling.return_value = dummy

        opt = NetworkOptimizer()
        report = opt.optimize_all(skip_dns=True, skip_mtu=True)
        self.assertIn("1 need reboot", report.summary)
        self.assertIn("1 skipped (requires Administrator)", report.summary)
        self.assertIn("1 skipped", report.summary)
        self.assertIn("already optimal", report.summary)

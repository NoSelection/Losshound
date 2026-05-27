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
    def test_backup_and_load(self, mock_get_resp, mock_get_heuristics, mock_backup_adapter, mock_get_throttling, mock_get_mtu, mock_get_dns, mock_get_tcp, mock_check_admin, mock_save):
        mock_check_admin.return_value = True
        mock_get_tcp.return_value = TcpSettings()
        mock_get_dns.return_value = ("1.1.1.1", "8.8.8.8")
        mock_get_mtu.return_value = 1500
        mock_get_throttling.return_value = 10
        mock_backup_adapter.return_value = AdapterBackup("Ethernet", True, True)
        mock_get_heuristics.return_value = "disabled"
        mock_get_resp.return_value = 10

        opt = NetworkOptimizer()
        backup = opt.create_backup()

        self.assertEqual(backup.tcp_heuristics, "disabled")
        self.assertEqual(backup.system_responsiveness, 10)

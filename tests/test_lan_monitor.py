import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from losshound.core.lan_monitor import (
    get_local_network_info,
    get_subnet_ips,
    lookup_vendor,
    resolve_hostname_safe,
    parse_arp_table,
    scan_local_network,
)
from losshound.core.local_monitor import (
    get_pid_to_process_name,
    get_active_connections,
)

# Mock inputs
MOCK_ARP_OUTPUT = """
Interface: 192.168.1.100 --- 0x3
  Internet Address      Physical Address      Type
  192.168.1.1           1c-3b-f3-ea-bb-cc     dynamic   
  192.168.1.102         04-d9-f5-12-34-56     dynamic   
  192.168.1.255         ff-ff-ff-ff-ff-ff     static    
  224.0.0.22            01-00-5e-00-00-16     static    
"""

MOCK_TASKLIST_OUTPUT = """
"System Idle Process","0","Services","0","8 K"
"System","4","Services","0","3,876 K"
"chrome.exe","4888","Console","1","248,312 K"
"""

MOCK_NETSTAT_OUTPUT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       988
  TCP    192.168.1.100:54321    142.250.74.46:443      ESTABLISHED     4888
  TCP    [::]:135               [::]:0                 LISTENING       988
  UDP    0.0.0.0:5353           *:*                                    2140
"""


def test_get_local_network_info():
    mock_res = MagicMock()
    from tests.conftest import IPCONFIG_OUTPUT
    mock_res.stdout = IPCONFIG_OUTPUT.encode("cp850")
    
    with patch("subprocess.run", return_value=mock_res):
        info = get_local_network_info()
        assert info["ip"] == "192.168.1.100"
        assert info["mask"] == "255.255.255.0"


def test_get_subnet_ips():
    ips = get_subnet_ips("192.168.1.100")
    assert len(ips) == 253  # 1 to 254 excluding 100
    assert "192.168.1.1" in ips
    assert "192.168.1.100" not in ips
    assert ips[0] == "192.168.1.1"
    assert ips[-1] == "192.168.1.254"


def test_lookup_vendor():
    assert lookup_vendor("1c:3b:f3:ea:bb:cc") == "HP"
    assert lookup_vendor("04-d9-f5-12-34-56") == "ASUS"
    assert lookup_vendor("00-00-00-00-00-00") == "Unknown"


def test_resolve_hostname_safe():
    with patch("socket.gethostbyaddr", return_value=("router.local", [], [])):
        name = resolve_hostname_safe("192.168.1.1")
        assert name == "router.local"
        
    with patch("socket.gethostbyaddr", side_effect=Exception("Failed")):
        name = resolve_hostname_safe("192.168.1.99")
        assert name == ""


def test_resolve_mdns_name():
    from losshound.core.lan_monitor import resolve_mdns_name
    
    mock_socket = MagicMock()
    mock_payload = b"\x00\x00\x84\x00\x00\x01\x00\x01\x00\x00\x00\x00"
    mock_payload += b"\x03107\x011\x03168\x03192\x07in-addr\x04arpa\x00\x00\x0c\x00\x01"
    mock_payload += b"\xc0\x0c\x00\x0c\x00\x01\x00\x00\x00\xff\x00\x13"
    mock_payload += b"\x0btest-device\x05local\x00"
    
    mock_socket.recvfrom.return_value = (mock_payload, ("192.168.1.107", 5353))
    
    with patch("socket.socket", return_value=mock_socket):
        name = resolve_mdns_name("192.168.1.107")
        assert name == "test-device"


def test_parse_arp_table():
    mock_res = MagicMock()
    mock_res.stdout = MOCK_ARP_OUTPUT.encode("cp850")
    
    with patch("subprocess.run", return_value=mock_res):
        devices = parse_arp_table("192.168.1.100")
        assert len(devices) == 2
        assert devices[0]["ip"] == "192.168.1.1"
        assert devices[0]["mac"] == "1C-3B-F3-EA-BB-CC"
        assert devices[1]["ip"] == "192.168.1.102"
        assert devices[1]["mac"] == "04-D9-F5-12-34-56"


def test_scan_local_network():
    mock_ipconfig = MagicMock()
    from tests.conftest import IPCONFIG_OUTPUT
    mock_ipconfig.stdout = IPCONFIG_OUTPUT.encode("cp850")
    
    mock_arp = MagicMock()
    mock_arp.stdout = MOCK_ARP_OUTPUT.encode("cp850")
    
    def mock_subprocess_run(args, *argv, **kwargs):
        if "ipconfig" in args:
            return mock_ipconfig
        elif "arp" in args:
            return mock_arp
        # For pings inside the sweep
        return MagicMock()
        
    # Mocking HistoryStore
    mock_history = MagicMock()
    mock_history.get_devices.return_value = []
    
    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("socket.gethostbyaddr", return_value=("test-device", [], [])):
         
        devices = scan_local_network(mock_history)
        
        assert len(devices) == 2
        assert devices[0]["mac_address"] == "1C-3B-F3-EA-BB-CC"
        assert devices[0]["vendor"] == "HP"
        assert devices[0]["hostname"] == "test-device"
        
        # Verify db interaction
        assert mock_history.save_device.call_count == 2
        assert mock_history.save_alert.call_count == 2  # Both devices are new


def test_get_pid_to_process_name():
    mock_res = MagicMock()
    mock_res.stdout = MOCK_TASKLIST_OUTPUT.encode("cp850")
    
    with patch("subprocess.run", return_value=mock_res):
        pid_map = get_pid_to_process_name()
        assert pid_map[0] == "System Idle Process"
        assert pid_map[4] == "System"
        assert pid_map[4888] == "chrome.exe"


def test_get_active_connections():
    mock_tasklist = MagicMock()
    mock_tasklist.stdout = MOCK_TASKLIST_OUTPUT.encode("cp850")
    
    mock_netstat = MagicMock()
    mock_netstat.stdout = MOCK_NETSTAT_OUTPUT.encode("cp850")
    
    def mock_subprocess_run(args, *argv, **kwargs):
        if "tasklist" in args:
            return mock_tasklist
        elif "netstat" in args:
            return mock_netstat
        return MagicMock()
        
    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("socket.gethostbyaddr", return_value=("google.com", [], [])):
         
        conns = get_active_connections()
        
        assert len(conns) == 1
        assert conns[0]["process"] == "chrome.exe"
        assert conns[0]["protocol"] == "TCP"
        assert conns[0]["remote_ip"] == "142.250.74.46"
        assert conns[0]["remote_port"] == "443"
        assert conns[0]["state"] == "ESTABLISHED"
        assert conns[0]["resolved_name"] == "google.com"


def test_scan_local_network_fallbacks():
    mock_ipconfig = MagicMock()
    from tests.conftest import IPCONFIG_OUTPUT
    mock_ipconfig.stdout = IPCONFIG_OUTPUT.encode("cp850")
    
    mock_arp = MagicMock()
    mock_arp.stdout = MOCK_ARP_OUTPUT.encode("cp850")
    
    def mock_subprocess_run(args, *argv, **kwargs):
        if "ipconfig" in args:
            return mock_ipconfig
        elif "arp" in args:
            return mock_arp
        return MagicMock()
        
    mock_history = MagicMock()
    mock_history.get_devices.return_value = []
    
    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("socket.gethostbyaddr", side_effect=Exception("failed")), \
         patch("losshound.core.lan_monitor.resolve_netbios_name", return_value=""):
         
        devices = scan_local_network(mock_history)
        
        # devices[0] has mac 1C-3B-F3-EA-BB-CC (HP) -> should fall back to "HP Device"
        # devices[1] has mac 04-D9-F5-12-34-56 (ASUS) -> should fall back to "ASUS Device"
        assert devices[0]["hostname"] == "HP Device"
        assert devices[1]["hostname"] == "ASUS Device"


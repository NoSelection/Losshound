import socket
from unittest.mock import patch

from losshound.core.dns_checks import check_dns


def test_dns_success():
    fake_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('142.250.80.46', 0))]
    with patch("socket.getaddrinfo", return_value=fake_result):
        result = check_dns("google.com")
        assert result.resolved
        assert result.resolved_ip == "142.250.80.46"
        assert result.resolution_time_ms is not None
        assert result.error is None


def test_dns_failure():
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name not found")):
        result = check_dns("nonexistent.invalid")
        assert not result.resolved
        assert result.error is not None
        assert "Name not found" in result.error


def test_dns_timeout():
    with patch("socket.getaddrinfo", side_effect=socket.timeout()):
        result = check_dns("slow.example.com", timeout=0.1)
        assert not result.resolved
        assert "timed out" in result.error

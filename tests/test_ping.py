from datetime import datetime

from losshound.core.ping import _parse_ping_output
from tests.conftest import PING_SUCCESS_OUTPUT, PING_PARTIAL_LOSS_OUTPUT, PING_TIMEOUT_OUTPUT


def test_parse_success():
    result = _parse_ping_output(PING_SUCCESS_OUTPUT, "1.1.1.1", datetime.now(), 4)
    assert result.packets_sent == 4
    assert result.packets_received == 4
    assert result.loss_percent == 0.0
    assert result.rtt_min == 11.0
    assert result.rtt_max == 13.0
    assert result.rtt_avg == 12.0
    assert not result.timed_out
    assert result.is_healthy


def test_parse_partial_loss():
    result = _parse_ping_output(PING_PARTIAL_LOSS_OUTPUT, "8.8.8.8", datetime.now(), 4)
    assert result.packets_sent == 4
    assert result.packets_received == 2
    assert result.loss_percent == 50.0
    assert result.rtt_avg == 14.0
    assert not result.timed_out
    assert not result.is_healthy


def test_parse_timeout():
    result = _parse_ping_output(PING_TIMEOUT_OUTPUT, "192.168.1.1", datetime.now(), 4)
    assert result.packets_sent == 4
    assert result.packets_received == 0
    assert result.loss_percent == 100.0
    assert result.rtt_avg is None
    assert result.timed_out
    assert not result.is_healthy


def test_parse_jitter():
    result = _parse_ping_output(PING_SUCCESS_OUTPUT, "1.1.1.1", datetime.now(), 4)
    # RTT values: 12, 11, 13, 12 -> diffs: 1, 2, 1 -> mean = 1.333
    assert result.rtt_jitter is not None
    assert 1.0 <= result.rtt_jitter <= 2.0

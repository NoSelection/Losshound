from datetime import datetime
from pathlib import Path

import pytest

from losshound.core.isp_report import IspReportData
from losshound.core.isp_report_pdf import render_isp_report_pdf


def _minimal_data() -> IspReportData:
    return IspReportData(
        generated_at=datetime(2026, 5, 11, 18, 0, 0).isoformat(),
        report_period_hours=24,
        system_info={
            "os": "Windows-11", "hostname": "TEST",
            "default_gateway": "192.168.1.1",
            "active_adapters": [
                {"name": "Wi-Fi", "description": "Intel AX201",
                 "link_speed": "866 Mbps"},
            ],
        },
        total_observations=12,
        total_benchmarks=2,
        avg_latency_ms=18.4,
        avg_jitter_ms=2.1,
        avg_loss_pct=0.3,
        max_latency_ms=45.0,
        max_loss_pct=2.0,
        avg_dns_ms=11.0,
        avg_score=87.0,
        latest_grade="B",
        issue_counts={"lan_issue": 1, "dns_issue": 2},
    )


def test_renders_pdf_to_path(tmp_path: Path):
    data = _minimal_data()
    out = tmp_path / "report.pdf"

    returned = render_isp_report_pdf(data, out)

    assert returned == out
    assert out.exists()
    assert out.stat().st_size > 0
    with out.open("rb") as f:
        head = f.read(5)
    assert head == b"%PDF-", f"PDF magic header missing, got {head!r}"


def test_pdf_includes_hostname_and_score(tmp_path: Path):
    pdfminer = pytest.importorskip("pdfminer.high_level")
    data = _minimal_data()
    out = tmp_path / "report.pdf"
    render_isp_report_pdf(data, out)

    text = pdfminer.extract_text(str(out))
    assert "TEST" in text  # hostname
    assert "87" in text    # score
    assert "lan_issue" in text or "LAN" in text


def test_pdf_embeds_latency_chart_when_observations_present(tmp_path: Path):
    data = _minimal_data()
    data.observations = [
        {"timestamp": f"2026-05-11T17:{m:02d}:00", "gateway_ip": "192.168.1.1",
         "gateway_loss": 0.0, "gateway_rtt": 1.5,
         "public_loss": 0.0, "public_rtt": 15.0 + m,
         "dns_failures": 0, "dns_total": 2}
        for m in range(0, 30, 2)
    ]
    out = tmp_path / "report.pdf"
    render_isp_report_pdf(data, out)

    # Quick sanity: PDF grows when a chart is embedded (vs. text-only cover).
    text_only_size = tmp_path / "small.pdf"
    data2 = _minimal_data()
    data2.observations = []
    render_isp_report_pdf(data2, text_only_size)

    assert out.stat().st_size > text_only_size.stat().st_size + 5000, (
        f"Chart not embedded: {out.stat().st_size} vs {text_only_size.stat().st_size}"
    )

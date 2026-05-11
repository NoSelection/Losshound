"""ISP report renderer — produces a polished PDF with charts."""

from __future__ import annotations

import logging
from pathlib import Path

from losshound.core.isp_report import IspReportData

logger = logging.getLogger(__name__)


def render_isp_report_pdf(data: IspReportData, output_path: Path) -> Path:
    """Render ``data`` as a styled PDF written to ``output_path``.

    Returns the output path on success. Raises ImportError if reportlab
    or matplotlib are missing, OSError on I/O failures.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate
    except ImportError as exc:
        raise ImportError(
            "reportlab is required for PDF export. "
            "Install with: pip install reportlab>=4.0"
        ) from exc

    output_path = Path(output_path)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=2 * 28, rightMargin=2 * 28,
        topMargin=2 * 28, bottomMargin=2 * 28,
        title="Losshound ISP Report",
        author="Losshound",
    )
    story = []
    _build_cover_page(data, story, getSampleStyleSheet())
    doc.build(story)
    return output_path


def _build_cover_page(data, story, styles):
    from reportlab.platypus import Paragraph, Spacer

    title_style = styles["Title"]
    body_style = styles["BodyText"]

    story.append(Paragraph("Losshound — ISP Network Quality Report", title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Generated: {data.generated_at[:19]}<br/>"
        f"Report period: last {data.report_period_hours} hours<br/>"
        f"Score: {data.avg_score:.0f}/100 (Grade {data.latest_grade or 'N/A'})"
        if data.avg_score is not None
        else f"Generated: {data.generated_at[:19]}<br/>"
             f"Report period: last {data.report_period_hours} hours",
        body_style,
    ))
    story.append(Spacer(1, 24))

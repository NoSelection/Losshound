from datetime import datetime
from pathlib import Path

from losshound.core.alerts import AlertEngine, AlertEvent
from losshound.core.config import AlertsConfig
from losshound.core.models import Diagnosis, DiagnosisCategory
from losshound.storage.history import HistoryStore


def _store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "h.db")


def _diag(category: DiagnosisCategory, ts: datetime) -> Diagnosis:
    return Diagnosis(
        timestamp=ts, category=category,
        summary="test", explanation="",
        confidence="high", evidence={},
    )


def test_healthy_diagnosis_returns_none(tmp_path: Path):
    store = _store(tmp_path)
    try:
        engine = AlertEngine(AlertsConfig(), store)
        result = engine.feed(_diag(DiagnosisCategory.HEALTHY, datetime.now()))
        assert result is None
    finally:
        store.close()

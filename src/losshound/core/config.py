from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILENAME = "config.default.json"
USER_CONFIG_FILENAME = "config.json"


def _app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    path = Path(base) / "Losshound"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class DiagnosisConfig:
    gateway_loss_threshold: float = 20.0
    public_loss_threshold: float = 20.0
    dns_failure_threshold: float = 0.5
    latency_warning_ms: float = 150.0
    jitter_warning_ms: float = 50.0
    route_change_sensitivity: int = 3
    timeout_burst_threshold: int = 3
    min_observations: int = 3
    window_minutes: int = 10


@dataclass
class AppConfig:
    ping_interval_seconds: int = 30
    dns_interval_seconds: int = 60
    route_interval_seconds: int = 300
    history_retention_hours: int = 24
    public_ping_targets: list[str] = field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])
    dns_test_hostnames: list[str] = field(default_factory=lambda: ["google.com", "chatgpt.com"])
    tracert_target: str = "8.8.8.8"
    tracert_max_hops: int = 20
    ping_count: int = 4
    ping_timeout_ms: int = 2000
    auto_benchmark_interval_minutes: int = 60
    diagnosis: DiagnosisConfig = field(default_factory=DiagnosisConfig)
    log_level: str = "INFO"

    def to_dict(self) -> dict:
        return asdict(self)


def _find_default_config() -> Optional[Path]:
    """Look for config.default.json relative to the package or CWD."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / DEFAULT_CONFIG_FILENAME,
        Path.cwd() / DEFAULT_CONFIG_FILENAME,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from file, falling back to defaults."""
    data = {}

    if config_path and Path(config_path).is_file():
        source = Path(config_path)
    else:
        user_config = _app_data_dir() / USER_CONFIG_FILENAME
        if user_config.is_file():
            source = user_config
        else:
            source = _find_default_config()

    if source:
        try:
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded config from %s", source)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load config from %s: %s", source, exc)

    diag_data = data.pop("diagnosis", {})
    diag = DiagnosisConfig(**{
        k: v for k, v in diag_data.items()
        if k in DiagnosisConfig.__dataclass_fields__
    })

    config = AppConfig(**{
        k: v for k, v in data.items()
        if k in AppConfig.__dataclass_fields__ and k != "diagnosis"
    })
    config.diagnosis = diag
    return config


def save_config(config: AppConfig, config_path: Optional[str] = None) -> Path:
    """Save configuration to file."""
    if config_path:
        dest = Path(config_path)
    else:
        dest = _app_data_dir() / USER_CONFIG_FILENAME

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=4)
    logger.info("Saved config to %s", dest)
    return dest

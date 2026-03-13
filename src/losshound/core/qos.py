"""Per-application QoS (Quality of Service) policy manager for Windows.

Uses PowerShell New-NetQosPolicy / Get-NetQosPolicy / Remove-NetQosPolicy
to create DSCP-based traffic prioritization rules.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from losshound.core.config import _app_data_dir

logger = logging.getLogger(__name__)

# DSCP priority presets (higher = more priority in most routers)
PRIORITY_PRESETS = {
    "Realtime":    46,  # EF  — VoIP, gaming
    "High":        34,  # AF41 — video streaming, competitive gaming
    "Normal":      0,   # Best effort (default)
    "Low":         10,  # AF11 — background downloads, updates
    "Bulk":        8,   # CS1  — torrents, backups
}

PRESET_DESCRIPTIONS = {
    "Realtime": "Lowest latency — VoIP, competitive gaming, remote desktop",
    "High": "Prioritized — video calls, streaming, important apps",
    "Normal": "Default best-effort — web browsing, general apps",
    "Low": "Deprioritized — background downloads, auto-updates",
    "Bulk": "Lowest priority — torrents, large backups",
}


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@dataclass
class QosRule:
    """A single QoS policy rule."""
    name: str
    app_path: str           # e.g. "chrome.exe" or full path
    priority_preset: str    # key in PRIORITY_PRESETS
    dscp_value: int
    active: bool = True
    note: str = ""


@dataclass
class QosResult:
    """Result of applying/removing a QoS rule."""
    rule_name: str
    success: bool
    action: str             # "created", "removed", "updated", "failed"
    message: str = ""


def check_admin() -> bool:
    """Check if running with admin privileges."""
    proc = _run([
        "powershell", "-NoProfile", "-Command",
        "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]"
        "::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
    ])
    return proc.stdout.strip().lower() == "true"


def get_existing_policies() -> list[dict]:
    """List all current NetQosPolicy entries."""
    proc = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-NetQosPolicy | Select-Object Name, AppPathNameMatchCondition, "
        "DSCPAction, ThrottleRateActionBitsPerSecond, PriorityValue8021Action "
        "| ConvertTo-Json -Depth 3",
    ])
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return data
    except json.JSONDecodeError:
        return []


def apply_rule(rule: QosRule) -> QosResult:
    """Create or update a QoS policy for an application."""
    if not check_admin():
        return QosResult(
            rule_name=rule.name,
            success=False,
            action="failed",
            message="Administrator privileges required to create QoS policies",
        )

    policy_name = f"Losshound_{rule.name}"

    # Remove existing policy with same name first
    _run([
        "powershell", "-NoProfile", "-Command",
        f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false "
        f"-ErrorAction SilentlyContinue",
    ])

    # Extract just the exe name from full path
    app_name = Path(rule.app_path).name if "\\" in rule.app_path or "/" in rule.app_path else rule.app_path

    # Create new policy
    proc = _run([
        "powershell", "-NoProfile", "-Command",
        f"New-NetQosPolicy -Name '{policy_name}' "
        f"-AppPathNameMatchCondition '{app_name}' "
        f"-DSCPAction {rule.dscp_value} "
        f"-PolicyStore ActiveStore "
        f"-ErrorAction Stop",
    ])

    if proc.returncode == 0:
        return QosResult(
            rule_name=rule.name,
            success=True,
            action="created",
            message=f"QoS policy applied: {app_name} -> DSCP {rule.dscp_value} ({rule.priority_preset})",
        )
    else:
        error = proc.stderr.strip() or proc.stdout.strip()
        return QosResult(
            rule_name=rule.name,
            success=False,
            action="failed",
            message=error[:200],
        )


def remove_rule(rule_name: str) -> QosResult:
    """Remove a Losshound QoS policy."""
    if not check_admin():
        return QosResult(
            rule_name=rule_name,
            success=False,
            action="failed",
            message="Administrator privileges required",
        )

    policy_name = f"Losshound_{rule_name}"
    proc = _run([
        "powershell", "-NoProfile", "-Command",
        f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false -ErrorAction Stop",
    ])

    if proc.returncode == 0:
        return QosResult(
            rule_name=rule_name, success=True, action="removed",
            message=f"Policy '{policy_name}' removed",
        )
    else:
        error = proc.stderr.strip() or proc.stdout.strip()
        return QosResult(
            rule_name=rule_name, success=False, action="failed",
            message=error[:200],
        )


def remove_all_losshound_policies() -> list[QosResult]:
    """Remove all QoS policies created by Losshound."""
    policies = get_existing_policies()
    results = []
    for p in policies:
        name = p.get("Name", "")
        if name.startswith("Losshound_"):
            short_name = name[len("Losshound_"):]
            results.append(remove_rule(short_name))
    return results


# ------------------------------------------------------------------
# Persistent rule storage (JSON file)
# ------------------------------------------------------------------

_RULES_FILE = "qos_rules.json"


def _rules_path() -> Path:
    return _app_data_dir() / _RULES_FILE


def load_saved_rules() -> list[QosRule]:
    """Load saved QoS rules from disk."""
    path = _rules_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            QosRule(
                name=r["name"],
                app_path=r["app_path"],
                priority_preset=r["priority_preset"],
                dscp_value=r["dscp_value"],
                active=r.get("active", True),
                note=r.get("note", ""),
            )
            for r in data
        ]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load QoS rules: %s", exc)
        return []


def save_rules(rules: list[QosRule]) -> None:
    """Persist QoS rules to disk."""
    data = [asdict(r) for r in rules]
    _rules_path().write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def apply_all_active_rules() -> list[QosResult]:
    """Apply all saved rules that are marked active."""
    rules = load_saved_rules()
    results = []
    for rule in rules:
        if rule.active:
            results.append(apply_rule(rule))
    return results

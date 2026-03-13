from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from losshound.core.config import _app_data_dir
from losshound.core.models import (
    Diagnosis,
    DiagnosisCategory,
    Observation,
    RouteSnapshot,
    observation_to_json,
    diagnosis_to_json,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    gateway_ip TEXT,
    gateway_loss REAL,
    gateway_rtt_avg REAL,
    public_loss_avg REAL,
    public_rtt_avg REAL,
    dns_fail_count INTEGER DEFAULT 0,
    dns_total_count INTEGER DEFAULT 0,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    explanation TEXT,
    confidence TEXT,
    evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS route_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    target TEXT,
    hops_json TEXT,
    completed INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations(timestamp);
CREATE INDEX IF NOT EXISTS idx_diag_ts ON diagnoses(timestamp);
CREATE INDEX IF NOT EXISTS idx_route_ts ON route_snapshots(timestamp);
"""


class HistoryStore:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = _app_data_dir() / "history.db"
        self._db_path = db_path
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("History store opened at %s", db_path)

    def close(self):
        self._conn.close()

    def save_observation(self, obs: Observation) -> None:
        gw_loss = obs.gateway_ping.loss_percent if obs.gateway_ping else None
        gw_rtt = obs.gateway_ping.rtt_avg if obs.gateway_ping else None

        pub_losses = [p.loss_percent for p in obs.public_pings]
        pub_rtts = [p.rtt_avg for p in obs.public_pings if p.rtt_avg is not None]
        pub_loss_avg = sum(pub_losses) / len(pub_losses) if pub_losses else None
        pub_rtt_avg = sum(pub_rtts) / len(pub_rtts) if pub_rtts else None

        dns_fail = sum(1 for d in obs.dns_results if not d.resolved)
        dns_total = len(obs.dns_results)

        self._conn.execute(
            """INSERT INTO observations
               (timestamp, gateway_ip, gateway_loss, gateway_rtt_avg,
                public_loss_avg, public_rtt_avg, dns_fail_count, dns_total_count, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                obs.timestamp.isoformat(),
                obs.gateway_ip,
                gw_loss, gw_rtt,
                pub_loss_avg, pub_rtt_avg,
                dns_fail, dns_total,
                observation_to_json(obs),
            ),
        )
        self._conn.commit()

    def save_diagnosis(self, diag: Diagnosis) -> None:
        self._conn.execute(
            """INSERT INTO diagnoses
               (timestamp, category, summary, explanation, confidence, evidence_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                diag.timestamp.isoformat(),
                diag.category.value,
                diag.summary,
                diag.explanation,
                diag.confidence,
                json.dumps(diag.evidence),
            ),
        )
        self._conn.commit()

    def save_route_snapshot(self, snap: RouteSnapshot) -> None:
        hops_data = [
            {"hop": h.hop_number, "ip": h.ip, "rtt": h.rtt_samples}
            for h in snap.hops
        ]
        self._conn.execute(
            """INSERT INTO route_snapshots
               (timestamp, target, hops_json, completed)
               VALUES (?, ?, ?, ?)""",
            (
                snap.timestamp.isoformat(),
                snap.target,
                json.dumps(hops_data),
                1 if snap.completed else 0,
            ),
        )
        self._conn.commit()

    def get_recent_observations(self, minutes: int = 10) -> list[Observation]:
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        rows = self._conn.execute(
            "SELECT raw_json FROM observations WHERE timestamp > ? ORDER BY timestamp",
            (cutoff,),
        ).fetchall()

        results = []
        for (raw,) in rows:
            try:
                results.append(_deserialize_observation(raw))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.debug("Failed to deserialize observation: %s", exc)
        return results

    def get_recent_diagnoses(self, count: int = 50) -> list[dict]:
        rows = self._conn.execute(
            """SELECT timestamp, category, summary, explanation, confidence, evidence_json
               FROM diagnoses ORDER BY timestamp DESC LIMIT ?""",
            (count,),
        ).fetchall()

        return [
            {
                "timestamp": row[0],
                "category": row[1],
                "summary": row[2],
                "explanation": row[3],
                "confidence": row[4],
                "evidence": json.loads(row[5]) if row[5] else {},
            }
            for row in reversed(rows)
        ]

    def get_route_snapshots(self, hours: int = 24) -> list[RouteSnapshot]:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = self._conn.execute(
            """SELECT timestamp, target, hops_json, completed
               FROM route_snapshots WHERE timestamp > ?
               ORDER BY timestamp""",
            (cutoff,),
        ).fetchall()

        from losshound.core.models import RouteHop

        results = []
        for ts, target, hops_json, completed in rows:
            hops_data = json.loads(hops_json) if hops_json else []
            hops = [
                RouteHop(
                    hop_number=h["hop"],
                    ip=h.get("ip"),
                    rtt_samples=h.get("rtt", []),
                )
                for h in hops_data
            ]
            results.append(RouteSnapshot(
                target=target,
                timestamp=datetime.fromisoformat(ts),
                hops=hops,
                completed=bool(completed),
            ))
        return results

    def prune(self, retention_hours: int = 24) -> int:
        cutoff = (datetime.now() - timedelta(hours=retention_hours)).isoformat()
        total = 0
        for table in ["observations", "diagnoses", "route_snapshots"]:
            cursor = self._conn.execute(
                f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,)
            )
            total += cursor.rowcount
        self._conn.commit()
        if total:
            logger.info("Pruned %d old records", total)
        return total

    def export_report(self, hours: int = 1) -> dict:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        obs_rows = self._conn.execute(
            """SELECT timestamp, gateway_ip, gateway_loss, gateway_rtt_avg,
                      public_loss_avg, public_rtt_avg, dns_fail_count, dns_total_count
               FROM observations WHERE timestamp > ?
               ORDER BY timestamp DESC LIMIT 20""",
            (cutoff,),
        ).fetchall()

        diag_rows = self._conn.execute(
            """SELECT timestamp, category, summary, explanation, confidence
               FROM diagnoses WHERE timestamp > ?
               ORDER BY timestamp DESC LIMIT 10""",
            (cutoff,),
        ).fetchall()

        route_rows = self._conn.execute(
            """SELECT timestamp, target, hops_json, completed
               FROM route_snapshots
               ORDER BY timestamp DESC LIMIT 1""",
        ).fetchall()

        return {
            "generated_at": datetime.now().isoformat(),
            "observations": [
                {
                    "timestamp": r[0], "gateway_ip": r[1],
                    "gateway_loss": r[2], "gateway_rtt": r[3],
                    "public_loss": r[4], "public_rtt": r[5],
                    "dns_failures": r[6], "dns_total": r[7],
                }
                for r in obs_rows
            ],
            "diagnoses": [
                {
                    "timestamp": r[0], "category": r[1],
                    "summary": r[2], "explanation": r[3],
                    "confidence": r[4],
                }
                for r in diag_rows
            ],
            "latest_route": (
                json.loads(route_rows[0][2]) if route_rows and route_rows[0][2] else []
            ),
        }


def _deserialize_observation(raw_json: str) -> Observation:
    """Reconstruct an Observation from stored JSON."""
    from losshound.core.models import PingResult, DnsResult, RouteHop

    d = json.loads(raw_json)
    ts = datetime.fromisoformat(d["timestamp"])

    gw_ping = None
    if d.get("gateway_ping"):
        gp = d["gateway_ping"]
        gw_ping = PingResult(
            target=gp["target"],
            timestamp=datetime.fromisoformat(gp["timestamp"]),
            packets_sent=gp["packets_sent"],
            packets_received=gp["packets_received"],
            loss_percent=gp["loss_percent"],
            rtt_min=gp.get("rtt_min"),
            rtt_avg=gp.get("rtt_avg"),
            rtt_max=gp.get("rtt_max"),
            rtt_jitter=gp.get("rtt_jitter"),
            timed_out=gp.get("timed_out", False),
            error=gp.get("error"),
        )

    pub_pings = []
    for pp in d.get("public_pings", []):
        pub_pings.append(PingResult(
            target=pp["target"],
            timestamp=datetime.fromisoformat(pp["timestamp"]),
            packets_sent=pp["packets_sent"],
            packets_received=pp["packets_received"],
            loss_percent=pp["loss_percent"],
            rtt_min=pp.get("rtt_min"),
            rtt_avg=pp.get("rtt_avg"),
            rtt_max=pp.get("rtt_max"),
            rtt_jitter=pp.get("rtt_jitter"),
            timed_out=pp.get("timed_out", False),
            error=pp.get("error"),
        ))

    dns_results = []
    for dr in d.get("dns_results", []):
        dns_results.append(DnsResult(
            hostname=dr["hostname"],
            timestamp=datetime.fromisoformat(dr["timestamp"]),
            resolved=dr["resolved"],
            resolved_ip=dr.get("resolved_ip"),
            resolution_time_ms=dr.get("resolution_time_ms"),
            error=dr.get("error"),
        ))

    route_snapshot = None
    if d.get("route_snapshot"):
        rs = d["route_snapshot"]
        hops = [
            RouteHop(
                hop_number=h["hop_number"],
                ip=h.get("ip"),
                rtt_samples=h.get("rtt_samples", []),
            )
            for h in rs.get("hops", [])
        ]
        route_snapshot = RouteSnapshot(
            target=rs["target"],
            timestamp=datetime.fromisoformat(rs["timestamp"]),
            hops=hops,
            completed=rs.get("completed", True),
            error=rs.get("error"),
        )

    return Observation(
        timestamp=ts,
        gateway_ip=d.get("gateway_ip"),
        gateway_ping=gw_ping,
        public_pings=pub_pings,
        dns_results=dns_results,
        route_snapshot=route_snapshot,
    )

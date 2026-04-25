"""
tools/db_tool.py — SQLite persistence layer for leads by sector.

Schema:
  campaigns — one row per pipeline run
  leads     — every qualified lead, linked to campaign + sector

No external dependencies — uses stdlib sqlite3.
DB location: output/leads.db (co-located with Excel outputs).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence

from models import QualifiedLead, RunReport

_DB_PATH = Path("output") / "leads.db"

# ──────────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_name TEXT NOT NULL,
    city          TEXT NOT NULL DEFAULT '',
    country       TEXT NOT NULL DEFAULT 'Colombia',
    run_at        TEXT NOT NULL,
    duration_secs REAL NOT NULL DEFAULT 0,
    total_raw     INTEGER NOT NULL DEFAULT 0,
    hot_count     INTEGER NOT NULL DEFAULT 0,
    warm_count    INTEGER NOT NULL DEFAULT 0,
    cold_count    INTEGER NOT NULL DEFAULT 0,
    excel_path    TEXT NOT NULL DEFAULT '',
    config_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     INTEGER NOT NULL REFERENCES campaigns(id),
    name            TEXT NOT NULL,
    sector          TEXT NOT NULL DEFAULT '',
    tier            TEXT NOT NULL CHECK(tier IN ('HOT','WARM','COLD')),
    final_score     REAL NOT NULL DEFAULT 0,
    contact_priority INTEGER NOT NULL DEFAULT 999,
    phone           TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    whatsapp        TEXT NOT NULL DEFAULT '',
    website         TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    place_id        TEXT NOT NULL DEFAULT '',
    rating          REAL NOT NULL DEFAULT 0,
    reviews_count   INTEGER NOT NULL DEFAULT 0,
    hormozi_score   REAL NOT NULL DEFAULT 0,
    hormozi_label   TEXT NOT NULL DEFAULT '',
    pitch_hook      TEXT NOT NULL DEFAULT '',
    action_line     TEXT NOT NULL DEFAULT '',
    entry_channel   TEXT NOT NULL DEFAULT '',
    lead_summary    TEXT NOT NULL DEFAULT '',
    digital_maturity TEXT NOT NULL DEFAULT '',
    estimated_size  TEXT NOT NULL DEFAULT '',
    timing_summary  TEXT NOT NULL DEFAULT '',
    inserted_at     TEXT NOT NULL,
    raw_json        TEXT NOT NULL DEFAULT '{}',
    UNIQUE(campaign_id, place_id, name)
);

CREATE INDEX IF NOT EXISTS idx_leads_sector ON leads(sector);
CREATE INDEX IF NOT EXISTS idx_leads_tier ON leads(tier);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);
"""


# ──────────────────────────────────────────────────────────────────
# Connection helper
# ──────────────────────────────────────────────────────────────────


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


# ──────────────────────────────────────────────────────────────────
# Write: persist a pipeline run
# ──────────────────────────────────────────────────────────────────


def save_campaign_leads(
    leads: Sequence[QualifiedLead],
    report: RunReport,
    city: str = "",
    country: str = "Colombia",
    excel_path: str = "",
    config_snapshot: dict[str, object] | None = None,
    db_path: Path | None = None,
) -> int:
    conn = _get_conn(db_path)
    now = datetime.now().isoformat()

    safe_config: dict[str, object] = dict(config_snapshot or {})
    key_pat = re.compile(r"(?i)(api_key|secret|token|password)")
    for k in list(safe_config.keys()):
        if key_pat.search(k):
            safe_config[k] = "***"

    try:
        cur = conn.execute(
            """INSERT INTO campaigns
               (campaign_name, city, country, run_at, duration_secs,
                total_raw, hot_count, warm_count, cold_count,
                excel_path, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.campaign_name,
                city,
                country,
                now,
                report.duration_seconds,
                report.total_raw,
                report.hot_count,
                report.warm_count,
                report.cold_count,
                excel_path,
                json.dumps(safe_config, ensure_ascii=False, default=str),
            ),
        )
        campaign_id: int = cur.lastrowid or 0

        for lead in leads:
            emails = "; ".join(
                lead.emails_scraped or ([lead.email] if lead.email else [])
            )
            wa = lead.whatsapp_number or ("" if not lead.has_whatsapp else lead.phone)

            conn.execute(
                """INSERT OR IGNORE INTO leads
                   (campaign_id, name, sector, tier, final_score, contact_priority,
                    phone, email, whatsapp, website, address, city, source, place_id,
                    rating, reviews_count, hormozi_score, hormozi_label,
                    pitch_hook, action_line, entry_channel,
                    lead_summary, digital_maturity, estimated_size,
                    timing_summary, inserted_at, raw_json)
                   VALUES (?,?,?,?,?,?, ?,?,?,?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?,?)""",
                (
                    campaign_id,
                    lead.name,
                    lead.main_sector or "",
                    lead.tier,
                    lead.final_score,
                    lead.contact_priority,
                    lead.phone,
                    emails,
                    wa,
                    lead.website,
                    lead.address,
                    city,
                    lead.source,
                    lead.place_id,
                    lead.rating,
                    lead.reviews_count,
                    lead.profile.hormozi_score,
                    lead.profile.hormozi_label,
                    lead.profile.pitch_hook,
                    lead.profile.cardone_action_line,
                    lead.profile.cardone_entry_channel,
                    lead.lead_summary,
                    lead.digital_maturity,
                    lead.estimated_size,
                    getattr(lead.visit_timing, "timing_summary", ""),
                    now,
                    json.dumps(
                        lead.model_dump(mode="json"),
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            )

        conn.commit()
        return campaign_id

    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────
# Read: query leads
# ──────────────────────────────────────────────────────────────────


def query_leads(
    sector: str | None = None,
    tier: str | None = None,
    city: str | None = None,
    campaign_name: str | None = None,
    min_score: float | None = None,
    limit: int = 100,
    db_path: Path | None = None,
) -> list[dict[str, object]]:
    conn = _get_conn(db_path)
    try:
        clauses: list[str] = []
        params: list[object] = []

        if sector:
            clauses.append("l.sector LIKE ?")
            params.append(f"%{sector}%")
        if tier:
            clauses.append("l.tier = ?")
            params.append(tier.upper())
        if city:
            clauses.append("l.city LIKE ?")
            params.append(f"%{city}%")
        if campaign_name:
            clauses.append("c.campaign_name LIKE ?")
            params.append(f"%{campaign_name}%")
        if min_score is not None:
            clauses.append("l.final_score >= ?")
            params.append(min_score)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        sql = f"""
            SELECT l.*, c.campaign_name, c.city as campaign_city, c.run_at
            FROM leads l
            JOIN campaigns c ON c.id = l.campaign_id
            {where}
            ORDER BY l.final_score DESC
            LIMIT ?
        """

        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]  # type: ignore[arg-type]

    finally:
        conn.close()


def get_sector_summary(db_path: Path | None = None) -> list[dict[str, object]]:
    conn = _get_conn(db_path)
    try:
        sql = """
            SELECT
                l.sector,
                COUNT(*)                          AS total,
                SUM(CASE WHEN l.tier='HOT'  THEN 1 ELSE 0 END) AS hot,
                SUM(CASE WHEN l.tier='WARM' THEN 1 ELSE 0 END) AS warm,
                SUM(CASE WHEN l.tier='COLD' THEN 1 ELSE 0 END) AS cold,
                ROUND(AVG(l.final_score), 2)      AS avg_score,
                COUNT(DISTINCT l.campaign_id)      AS campaigns
            FROM leads l
            GROUP BY l.sector
            ORDER BY total DESC
        """
        rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]  # type: ignore[arg-type]

    finally:
        conn.close()


def get_campaign_history(db_path: Path | None = None) -> list[dict[str, object]]:
    conn = _get_conn(db_path)
    try:
        rows = conn.execute("SELECT * FROM campaigns ORDER BY run_at DESC").fetchall()
        return [dict(row) for row in rows]  # type: ignore[arg-type]

    finally:
        conn.close()

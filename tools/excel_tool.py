"""
tools/excel_tool.py — Export qualified leads to a formatted Excel workbook.

Sheets:
  1. HOT     — Tier 1 leads (red header)
  2. WARM    — Tier 2 leads (orange header)
  3. COLD    — Tier 3 leads (blue header)
  4. TODOS   — All leads combined
  5. RESUMEN — Campaign summary / RunReport

Column groups (applied to HOT / WARM / COLD / TODOS):
  Contact | Location | Ratings | Digital | Profile | Timing | Score

Color coding rows by tier:
  HOT  → pastel red   #FFCCCC
  WARM → pastel orange #FFE5B4
  COLD → pastel blue   #CCE5FF
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Sequence

from models import QualifiedLead, RunReport

# Conditional import — openpyxl must be installed
try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    _OPENPYXL_OK = True
except ImportError:  # pragma: no cover
    _OPENPYXL_OK = False


# ──────────────────────────────────────────────────────────────────
# Colour palette
# ──────────────────────────────────────────────────────────────────

_TIER_ROW_FILL = {
    "HOT": PatternFill("solid", fgColor="FFCCCC") if _OPENPYXL_OK else None,
    "WARM": PatternFill("solid", fgColor="FFE5B4") if _OPENPYXL_OK else None,
    "COLD": PatternFill("solid", fgColor="CCE5FF") if _OPENPYXL_OK else None,
}
_HEADER_FILL = {
    "HOT": PatternFill("solid", fgColor="C00000") if _OPENPYXL_OK else None,
    "WARM": PatternFill("solid", fgColor="E26B0A") if _OPENPYXL_OK else None,
    "COLD": PatternFill("solid", fgColor="1F4E79") if _OPENPYXL_OK else None,
    "TODOS": PatternFill("solid", fgColor="2E4057") if _OPENPYXL_OK else None,
    "RESUMEN": PatternFill("solid", fgColor="375623") if _OPENPYXL_OK else None,
}
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=10) if _OPENPYXL_OK else None
_THIN = Side(style="thin") if _OPENPYXL_OK else None
_BORDER = (
    Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN) if _OPENPYXL_OK else None
)

# ──────────────────────────────────────────────────────────────────
# Column definitions  (header, field_extractor)
# ──────────────────────────────────────────────────────────────────


def _get(lead: QualifiedLead, *attrs):
    obj = lead
    for attr in attrs:
        obj = getattr(obj, attr, None)
        if obj is None:
            return ""
    return obj if obj is not None else ""


_COLUMNS = [
    # fmt: off
    # Contact
    ("Nombre",           lambda l: l.name),
    ("Teléfono",         lambda l: l.phone),
    ("WhatsApp",         lambda l: l.whatsapp_number or ("Sí" if l.has_whatsapp else "")),
    ("Emails",           lambda l: "; ".join(l.emails_scraped or ([l.email] if l.email else []))),
    ("Sitio Web",        lambda l: l.website),
    # Location
    ("Dirección",        lambda l: l.address),
    ("Ciudad",           lambda l: ""),           # filled from config at runtime
    # Ratings
    ("Rating Google",    lambda l: l.rating),
    ("Reseñas",          lambda l: l.reviews_count),
    # Digital
    ("Madurez Digital",  lambda l: _get(l, "digital_maturity")),
    ("Stack Tech",       lambda l: "; ".join(l.technology_stack or [])),
    ("Redes Sociales",   lambda l: "; ".join(f"{k}: {v}" for k, v in (l.social_links or {}).items())),
    # Profile
    ("Tamaño Est.",      lambda l: _get(l, "estimated_size")),
    ("Sector",           lambda l: _get(l, "main_sector")),
    ("Tipo Comprador",   lambda l: _get(l, "profile", "challenger_buyer_type")),
    ("Score Hormozi",    lambda l: _get(l, "profile", "hormozi_score")),
    ("Label Hormozi",    lambda l: _get(l, "profile", "hormozi_label")),
    ("Compromiso",       lambda l: _get(l, "profile", "cardone_commitment")),
    ("Canal Entrada",    lambda l: _get(l, "profile", "cardone_entry_channel")),
    ("Objeción Princ.",  lambda l: _get(l, "profile", "cardone_objection")),
    ("Pitch Hook",       lambda l: _get(l, "profile", "pitch_hook")),
    ("Acción Propuesta", lambda l: _get(l, "profile", "cardone_action_line")),
    # Timing
    ("Mejor Horario",    lambda l: _get(l, "visit_timing", "timing_summary")),
    ("Conf. Horario",    lambda l: _get(l, "visit_timing", "timing_confidence")),
    # Score + Tier
    ("Score Final",      lambda l: round(l.final_score, 2) if l.final_score else ""),
    ("Tier",             lambda l: l.tier),
    ("Prioridad",        lambda l: l.contact_priority),
    ("Razón Descarte",   lambda l: l.discard_reason or ""),
    # Source metadata
    ("Fuente",           lambda l: l.source),
    ("Place ID",         lambda l: l.place_id),
    # fmt: on
]


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────


def export_to_excel(
    leads: Sequence[QualifiedLead],
    report: RunReport,
    output_dir: str = "output",
    filename_prefix: str = "prospectos",
) -> str:
    """
    Export leads + report to an Excel workbook.

    Returns:
        Absolute path of the created .xlsx file.
    """
    if not _OPENPYXL_OK:
        raise ImportError("openpyxl is required. Run: pip install openpyxl")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^\w]", "_", report.campaign_name.lower())
    out_path = Path(output_dir) / f"{filename_prefix}_{slug}_{ts}.xlsx"

    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    # Tier sheets
    hot_leads = [l for l in leads if l.tier == "HOT"]
    warm_leads = [l for l in leads if l.tier == "WARM"]
    cold_leads = [l for l in leads if l.tier == "COLD"]

    _write_leads_sheet(wb, "🔴 HOT", hot_leads, "HOT")
    _write_leads_sheet(wb, "🟠 WARM", warm_leads, "WARM")
    _write_leads_sheet(wb, "🔵 COLD", cold_leads, "COLD")
    _write_leads_sheet(wb, "📋 TODOS", list(leads), "TODOS")
    _write_summary_sheet(wb, report)

    wb.save(out_path)
    return str(out_path)


# ──────────────────────────────────────────────────────────────────
# Sheet writers
# ──────────────────────────────────────────────────────────────────


def _write_leads_sheet(
    wb: "Workbook",
    sheet_name: str,
    leads: list[QualifiedLead],
    tier_key: str,
) -> None:
    ws = wb.create_sheet(title=sheet_name)
    header_fill = _HEADER_FILL.get(tier_key, _HEADER_FILL["TODOS"])
    row_fill = _TIER_ROW_FILL.get(tier_key)

    # Header row
    headers = [col[0] for col in _COLUMNS]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = header_fill  # type: ignore[arg-type]
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = _BORDER  # type: ignore[arg-type]

    ws.row_dimensions[1].height = 30

    # Data rows
    for row_idx, lead in enumerate(leads, start=2):
        fill = _TIER_ROW_FILL.get(lead.tier, row_fill)
        for col_idx, (_, extractor) in enumerate(_COLUMNS, start=1):
            try:
                value = extractor(lead)
            except Exception:  # noqa: BLE001
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if fill:
                cell.fill = fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = _BORDER  # type: ignore[arg-type]

    # Auto-fit columns (approximate)
    for col_idx in range(1, len(headers) + 1):
        max_len = max(
            (
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(1, ws.max_row + 1)
            ),
            default=10,
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

    # Freeze header
    ws.freeze_panes = "A2"


def _write_summary_sheet(wb: "Workbook", report: RunReport) -> None:
    ws = wb.create_sheet(title="📊 RESUMEN")
    header_fill = _HEADER_FILL["RESUMEN"]

    rows = [
        ("Campo", "Valor"),
        ("Campaña", report.campaign_name),
        ("Fecha / Hora", report.timestamp),
        ("Leads raw captados", report.total_raw),
        ("Leads únicos (post-dedup)", report.total_after_dedup),
        ("HOT", report.hot_count),
        ("WARM", report.warm_count),
        ("COLD", report.cold_count),
        ("Duración (segundos)", report.duration_seconds),
        ("Iteraciones", report.iterations),
        ("Leads por iteración", ", ".join(str(n) for n in report.leads_per_iteration)),
    ]

    # Sources breakdown
    for source, count in report.sources_breakdown.items():
        rows.append((f"Fuente: {source}", count))

    # Error log
    if report.error_log:
        rows.append(("", ""))
        rows.append(("ERRORES", ""))
        for err in report.error_log:
            rows.append((err.get("step", "?"), err.get("message", "")))

    for row_idx, (key, val) in enumerate(rows, start=1):
        k_cell = ws.cell(row=row_idx, column=1, value=key)
        v_cell = ws.cell(row=row_idx, column=2, value=val)
        if row_idx == 1:
            for cell in (k_cell, v_cell):
                cell.font = _HEADER_FONT
                cell.fill = header_fill  # type: ignore[arg-type]
        k_cell.border = _BORDER  # type: ignore[arg-type]
        v_cell.border = _BORDER  # type: ignore[arg-type]

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 45
    ws.freeze_panes = "A2"

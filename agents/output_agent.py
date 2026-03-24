"""
agents/output_agent.py — Exports qualified leads + RunReport to Excel + JSON log.

Responsibilities:
  1. Call ExcelExportTool to generate the .xlsx file.
  2. Write run_log_{timestamp}.json with full audit trail.
  3. Print a Rich table summary to stdout.
  4. Return the output file path.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.table import Table

from config import AppSettings
from models import BusinessSummary, QualifiedLead, RunReport, SearchConfig

console = Console()


class OutputAgent:
    """Handles all output writing (Excel + console summary)."""

    @classmethod
    def process(
        cls,
        leads: Sequence[QualifiedLead],
        report: RunReport,
        config: SearchConfig,
        settings: AppSettings,  # noqa: ARG003 — reserved for future cloud upload
        business_summary: BusinessSummary | None = None,
        auto_generated_queries: Sequence[str] | None = None,
    ) -> str:
        agent = cls(config)
        return agent.run(
            list(leads),
            report,
            business_summary=business_summary,
            auto_generated_queries=list(auto_generated_queries or []),
        )

    def __init__(self, config: SearchConfig) -> None:
        self.config = config

    # ──────────────────────────────────────────────────────────────

    def run(
        self,
        leads: list[QualifiedLead],
        report: RunReport,
        business_summary: BusinessSummary | None = None,
        auto_generated_queries: list[str] | None = None,
    ) -> str:
        from tools.excel_tool import export_to_excel

        out_path = export_to_excel(
            leads=leads,
            report=report,
            output_dir="output",
            filename_prefix=self.config.output_filename,
        )

        log_path = self._write_run_log(
            leads,
            report,
            out_path,
            business_summary=business_summary,
            auto_generated_queries=auto_generated_queries or [],
        )
        self._print_summary(leads, report, out_path, log_path)
        return out_path

    # ──────────────────────────────────────────────────────────────

    def _write_run_log(
        self,
        leads: list[QualifiedLead],
        report: RunReport,
        excel_path: str,
        business_summary: BusinessSummary | None = None,
        auto_generated_queries: list[str] | None = None,
    ) -> str:
        """Write run_log_{timestamp}.json for audit and reproducibility."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"run_log_{ts}.json"
        log_path = Path("output") / log_filename

        # Strip API keys from config snapshot
        config_snapshot = self.config.model_dump()
        # Sanitise any field that looks like a key/token (extra safety)
        _KEY_PAT = re.compile(r"(?i)(api_key|secret|token|password)")
        for k in list(config_snapshot.keys()):
            if _KEY_PAT.search(k):
                config_snapshot[k] = "***"

        log_data = {
            "campaign_name": report.campaign_name,
            "timestamp": report.timestamp,
            "duration_seconds": report.duration_seconds,
            "iterations_used": report.iterations,
            "config_snapshot": config_snapshot,
            "report": report.model_dump(),
            "sources_breakdown": report.sources_breakdown,
            "leads_per_iteration": report.leads_per_iteration,
            "error_log": report.error_log,
            "excel_output": excel_path,
            "auto_generated_queries": list(auto_generated_queries or []),
            "business_summary": (
                business_summary.model_dump() if business_summary else None
            ),
            "leads_summary": [
                {
                    "name": l.name,
                    "tier": l.tier,
                    "final_score": l.final_score,
                    "contact_priority": l.contact_priority,
                    "source": l.source,
                }
                for l in sorted(leads, key=lambda l: l.contact_priority)
            ],
        }

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2, default=str)

        console.print(f"[dim]📋 Run log → {log_path}[/dim]")
        return str(log_path)

    # ──────────────────────────────────────────────────────────────

    def _print_summary(
        self,
        leads: list[QualifiedLead],
        report: RunReport,
        out_path: str,
        log_path: str = "",
    ) -> None:
        hot = [l for l in leads if l.tier == "HOT"]
        warm = [l for l in leads if l.tier == "WARM"]
        cold = [l for l in leads if l.tier == "COLD"]

        console.rule(f"[bold green] Campaña: {report.campaign_name}")

        # Stats table
        stats = Table(title="Resumen de prospectos", show_header=True)
        stats.add_column("Métrica", style="bold")
        stats.add_column("Valor", justify="right")

        stats.add_row("Total raw capturados", str(report.total_raw))
        stats.add_row("Únicos tras dedup", str(report.total_after_dedup))
        stats.add_row("[red]HOT[/red]", str(report.hot_count))
        stats.add_row("[orange1]WARM[/orange1]", str(report.warm_count))
        stats.add_row("[blue]COLD[/blue]", str(report.cold_count))
        stats.add_row("Duración", f"{report.duration_seconds:.1f}s")
        stats.add_row("Iteraciones", str(report.iterations))
        stats.add_row("Archivo generado", Path(out_path).name)

        console.print(stats)

        # Top 5 HOT leads
        if hot:
            top = Table(title="🔴 Top HOT leads", show_header=True)
            top.add_column("#", width=3)
            top.add_column("Nombre")
            top.add_column("Sector")
            top.add_column("Score", justify="right")
            top.add_column("Hormozi")
            top.add_column("Canal")

            for i, lead in enumerate(
                sorted(hot, key=lambda l: l.final_score, reverse=True)[:5], 1
            ):
                top.add_row(
                    str(i),
                    lead.name[:40],
                    (lead.main_sector or "")[:20],
                    str(lead.final_score),
                    lead.profile.hormozi_label,
                    lead.profile.cardone_entry_channel,
                )
            console.print(top)

        console.print(
            f"\n[bold green]✅ Excel exportado → [link={out_path}]{out_path}[/link]"
        )
        if log_path:
            console.print(
                f"[bold green]✅ Run log → [link={log_path}]{log_path}[/link]"
            )

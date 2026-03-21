"""
agents/output_agent.py — Exports qualified leads + RunReport to Excel.

Responsibilities:
  1. Call ExcelExportTool to generate the .xlsx file.
  2. Print a Rich table summary to stdout.
  3. Return the output file path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.table import Table

from config import AppSettings
from models import QualifiedLead, RunReport, SearchConfig

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
    ) -> str:
        agent = cls(config)
        return agent.run(list(leads), report)

    def __init__(self, config: SearchConfig) -> None:
        self.config = config

    # ──────────────────────────────────────────────────────────────

    def run(self, leads: list[QualifiedLead], report: RunReport) -> str:
        from tools.excel_tool import export_to_excel

        out_path = export_to_excel(
            leads=leads,
            report=report,
            output_dir="output",
            filename_prefix=self.config.output_filename,
        )

        self._print_summary(leads, report, out_path)
        return out_path

    # ──────────────────────────────────────────────────────────────

    def _print_summary(
        self,
        leads: list[QualifiedLead],
        report: RunReport,
        out_path: str,
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

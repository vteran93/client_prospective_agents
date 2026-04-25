"""
main.py — CLI entry point for the Growth Guard Prospecting System.

Usage:
  python main.py --config search_config.yaml
  python main.py --config search_config.yaml --dry-run
  python main.py --config search_config.yaml --max-leads 50 --llm openai
  python main.py --query-db --sector "Marketing Digital" --tier HOT

Options:
  --config       Path to search_config.yaml                  [required for run]
  --dry-run      Validate config + API keys only; don't run  [flag]
  --max-leads N  Override max_leads from config              [optional]
  --llm          Override llm.provider (bedrock|openai)      [optional]
  --no-scrape    Disable website scraping                    [flag]
  --query-db     Query stored leads instead of running pipeline [flag]
  --sectors      Show sector summary from DB                 [flag]
  --sector S     Filter by sector (with --query-db)          [optional]
  --tier T       Filter by tier (with --query-db)            [optional]
  --min-score N  Filter by minimum score (with --query-db)   [optional]
"""

from __future__ import annotations

import argparse
import sys
import traceback

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_BANNER = """
[bold green]╔══════════════════════════════════════════════════════╗
║     Growth Guard — Prospecting Intelligence System   ║
║     Framework: Hormozi · SEC · Cardone               ║
╚══════════════════════════════════════════════════════╝[/bold green]
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Growth Guard multi-agent B2B prospecting system",
    )
    parser.add_argument(
        "--config",
        required=False,
        metavar="PATH",
        help="Path to search_config.yaml (required for pipeline run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and API keys only; do not run the pipeline",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=None,
        metavar="N",
        help="Override max_leads from config",
    )
    parser.add_argument(
        "--llm",
        choices=["bedrock", "openai"],
        default=None,
        help="Override llm.provider from config",
    )
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Disable website scraping step",
    )
    parser.add_argument(
        "--query-db",
        action="store_true",
        help="Query stored leads from DB instead of running pipeline",
    )
    parser.add_argument(
        "--sectors",
        action="store_true",
        help="Show sector summary from DB",
    )
    parser.add_argument(
        "--sector",
        type=str,
        default=None,
        help="Filter by sector (with --query-db)",
    )
    parser.add_argument(
        "--tier",
        choices=["HOT", "WARM", "COLD"],
        default=None,
        help="Filter by tier (with --query-db)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Filter by minimum score (with --query-db)",
    )
    return parser.parse_args()


def _handle_db_query(args: argparse.Namespace) -> None:
    from tools.db_tool import get_sector_summary, query_leads

    if args.sectors:
        sectors = get_sector_summary()
        if not sectors:
            console.print("[yellow]No hay leads almacenados aún.")
            return
        table = Table(title="Leads por Sector", show_header=True)
        table.add_column("Sector", style="bold")
        table.add_column("Total", justify="right")
        table.add_column("[red]HOT", justify="right")
        table.add_column("[orange1]WARM", justify="right")
        table.add_column("[blue]COLD", justify="right")
        table.add_column("Avg Score", justify="right")
        table.add_column("Campañas", justify="right")
        for s in sectors:
            table.add_row(
                s["sector"] or "(sin sector)",
                str(s["total"]),
                str(s["hot"]),
                str(s["warm"]),
                str(s["cold"]),
                str(s["avg_score"]),
                str(s["campaigns"]),
            )
        console.print(table)
        return

    results = query_leads(
        sector=args.sector,
        tier=args.tier,
        min_score=args.min_score,
    )
    if not results:
        console.print("[yellow]No se encontraron leads con esos filtros.")
        return

    table = Table(title=f"Leads ({len(results)} resultados)", show_header=True)
    table.add_column("#", width=3)
    table.add_column("Nombre")
    table.add_column("Sector")
    table.add_column("Tier")
    table.add_column("Score", justify="right")
    table.add_column("Teléfono")
    table.add_column("WhatsApp")
    table.add_column("Canal")

    for i, row in enumerate(results, 1):
        table.add_row(
            str(i),
            (row["name"] or "")[:40],
            (row["sector"] or "")[:25],
            row["tier"],
            str(row["final_score"]),
            row["phone"],
            row["whatsapp"],
            row["entry_channel"],
        )
    console.print(table)


def main() -> None:
    args = parse_args()

    console.print(_BANNER)

    if args.query_db or args.sectors:
        _handle_db_query(args)
        return

    # ── Load config ─────────────────────────────────────────────
    from config import AppSettings, ConfigError, load_config, validate_api_keys

    if not args.config:
        console.print("[red bold]✗ --config es requerido para ejecutar el pipeline.")
        sys.exit(1)

    try:
        overrides: dict = {}
        if args.max_leads is not None:
            overrides["max_leads"] = args.max_leads
        if args.llm:
            overrides["llm_provider"] = args.llm
        if args.no_scrape:
            overrides["scrape_websites"] = False

        config = load_config(args.config, overrides)
        settings = AppSettings()
        validate_api_keys(config, settings)

    except ConfigError as exc:
        console.print(f"[red bold]✗ Error de configuración:[/red bold] {exc}")
        sys.exit(1)

    # ── Print campaign info ──────────────────────────────────────
    info = Table.grid(padding=(0, 2))
    info.add_row("[bold]Campaña[/bold]", config.campaign_name)
    info.add_row("[bold]Ciudad[/bold]", config.city)
    info.add_row(
        "[bold]Queries[/bold]",
        str(len(config.queries)) if config.queries else "auto-generadas",
    )
    info.add_row("[bold]Fuentes[/bold]", ", ".join(config.sources))
    info.add_row("[bold]Max leads[/bold]", str(config.max_leads))
    info.add_row(
        "[bold]Target HOT+WARM[/bold]", str(config.qualification.target_hot_warm)
    )
    info.add_row("[bold]LLM provider[/bold]", config.llm_provider)
    info.add_row("[bold]Scrape sitios[/bold]", "✓" if config.scrape_websites else "✗")
    if config.business_context:
        info.add_row(
            "[bold]Business context[/bold]",
            config.business_context.description[:60] + "...",
        )
        info.add_row(
            "[bold]Clientes ideales[/bold]",
            str(len(config.business_context.ideal_customers)),
        )
    console.print(
        Panel(info, title="[bold]Configuración de campaña[/bold]", border_style="cyan")
    )

    if args.dry_run:
        console.print(
            "[green bold]✓ Validación exitosa (--dry-run). No se ejecutó el pipeline."
        )
        sys.exit(0)

    # ── Run pipeline ─────────────────────────────────────────────
    console.print()
    console.print("[bold cyan]▶ Iniciando pipeline de prospección...")
    console.print()

    try:
        from crew import ProspectingCrew

        crew = ProspectingCrew(config, settings)
        qualified, report = crew.run()

        # Final summary already printed by OutputAgent
        console.print()
        console.print(
            f"[bold green]Pipeline completado en {report.duration_seconds:.1f}s — "
            f"{report.hot_count} HOT · {report.warm_count} WARM · {report.cold_count} COLD"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrumpido por el usuario.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red bold]✗ Error en el pipeline:[/red bold] {exc}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()

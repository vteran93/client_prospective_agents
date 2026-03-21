"""
main.py — CLI entry point for the Growth Guard Prospecting System.

Usage:
  python main.py --config search_config.yaml
  python main.py --config search_config.yaml --dry-run
  python main.py --config search_config.yaml --max-leads 50 --llm openai

Options:
  --config       Path to search_config.yaml                  [required]
  --dry-run      Validate config + API keys only; don't run  [flag]
  --max-leads N  Override max_leads from config              [optional]
  --llm          Override llm.provider (bedrock|openai)      [optional]
  --no-scrape    Disable website scraping                    [flag]
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
        required=True,
        metavar="PATH",
        help="Path to search_config.yaml",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    console.print(_BANNER)

    # ── Load config ─────────────────────────────────────────────
    from config import AppSettings, ConfigError, load_config, validate_api_keys

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
    info.add_row("[bold]Queries[/bold]", str(len(config.queries)))
    info.add_row("[bold]Fuentes[/bold]", ", ".join(config.sources))
    info.add_row("[bold]Max leads[/bold]", str(config.max_leads))
    info.add_row(
        "[bold]Target HOT+WARM[/bold]", str(config.qualification.target_hot_warm)
    )
    info.add_row("[bold]LLM provider[/bold]", config.llm_provider)
    info.add_row("[bold]Scrape sitios[/bold]", "✓" if config.scrape_websites else "✗")
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

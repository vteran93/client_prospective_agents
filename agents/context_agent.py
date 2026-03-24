"""
agents/context_agent.py — Scrapes reference URLs and generates a BusinessSummary.

Responsibilities (T034):
  1. Take BusinessContext from config.
  2. Scrape each reference_url using WebScraperTool.
  3. Combine description + scraped content into an LLM prompt.
  4. Generate BusinessSummary via with_structured_output.
  5. If ideal_customers are provided in config, copy them directly.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.language_models import BaseChatModel
from rich.console import Console

from config import AppSettings
from models import BusinessContext, BusinessSummary, SearchConfig

console = Console()

_CONTEXT_SYSTEM = """\
Eres un analista de inteligencia de negocios experto en el mercado latinoamericano.
Tu tarea es analizar la información de un negocio y generar un resumen estructurado
que permita identificar a sus clientes ideales y generar estrategias de prospección.

Reglas:
- Responde ÚNICAMENTE con el JSON estructurado solicitado.
- Basa tu análisis en los datos provistos; NO inventes información.
- Si un campo no puede ser inferido, usa cadena vacía o lista vacía.
- Todos los textos deben ser en español.
"""

_CONTEXT_HUMAN = """\
Analiza el siguiente negocio y genera un resumen estructurado para prospección comercial.

=== DESCRIPCIÓN DEL NEGOCIO ===
{description}

=== AUDIENCIA OBJETIVO ===
{target_audience}

=== CONTENIDO SCRAPEADO DE URLS DE REFERENCIA ===
{scraped_content}

=== INSTRUCCIONES ===
Genera un resumen estructurado con:
- core_offering: Descripción concisa del producto/servicio principal (1-2 oraciones)
- target_sectors: Lista de 5-10 sectores/industrias objetivo
- key_pain_points: Lista de 3-5 dolores principales que resuelve el negocio
- differentiators: Lista de 3-5 diferenciadores competitivos
- geographic_focus: Foco geográfico principal
{ideal_customers_instruction}
"""


class ContextAgent:
    """Scrapes reference URLs and generates a structured BusinessSummary."""

    @classmethod
    def process(
        cls,
        config: SearchConfig,
        settings: AppSettings,
        llm: BaseChatModel,
    ) -> BusinessSummary:
        bc = config.business_context
        if not bc:
            return BusinessSummary()

        console.print("[cyan]  🧠 ContextAgent: analizando contexto del negocio...")

        # Scrape reference URLs concurrently
        scraped_texts = cls._scrape_urls(bc.reference_urls)
        scraped_content = (
            "\n\n".join(scraped_texts)
            if scraped_texts
            else "(No hay contenido scrapeado disponible)"
        )

        # Truncate combined context to ~3000 chars
        raw_context = f"{bc.description}\n\n{scraped_content}"[:3000]

        # Decide ideal_customers instruction
        if bc.ideal_customers:
            ic_instruction = (
                "- ideal_customers: Copia exactamente estos perfiles de cliente ideal: "
                + json.dumps(bc.ideal_customers, ensure_ascii=False)
            )
        else:
            ic_instruction = (
                "- ideal_customers: Infiere 5-10 perfiles de cliente ideal basándote "
                "en la descripción del negocio, la audiencia objetivo y el contenido scrapeado. "
                "Cada perfil debe ser específico (tipo de empresa + tamaño + característica clave)."
            )

        messages = [
            {"role": "system", "content": _CONTEXT_SYSTEM},
            {
                "role": "user",
                "content": _CONTEXT_HUMAN.format(
                    description=bc.description,
                    target_audience=bc.target_audience or "(No especificada)",
                    scraped_content=scraped_content[:2000],
                    ideal_customers_instruction=ic_instruction,
                ),
            },
        ]

        try:
            structured_llm = llm.with_structured_output(BusinessSummary)
            summary: BusinessSummary = structured_llm.invoke(messages)
        except Exception as exc:
            console.print(f"[yellow]  ⚠ ContextAgent structured output fallback: {exc}")
            # Fallback: build a minimal summary from config data
            summary = BusinessSummary(
                core_offering=bc.description[:200],
                geographic_focus=f"{config.city}, {config.country}",
                ideal_customers=list(bc.ideal_customers),
            )

        # Override ideal_customers from config if provided (don't waste LLM tokens)
        if bc.ideal_customers:
            summary.ideal_customers = list(bc.ideal_customers)
            console.print(
                f"[dim]  📋 Clientes ideales del config: {len(summary.ideal_customers)} perfiles"
            )
        else:
            console.print(
                f"[dim]  🧠 Clientes ideales inferidos por LLM: {len(summary.ideal_customers)} perfiles"
            )

        summary.raw_context = raw_context
        console.print(
            f"[green]  ✓ ContextAgent: resumen generado ({len(summary.target_sectors)} sectores)"
        )
        return summary

    @classmethod
    def _scrape_urls(cls, urls: list[str]) -> list[str]:
        """Scrape reference URLs concurrently and return text summaries."""
        if not urls:
            return []

        from tools.scraper_tool import WebScraperTool

        results: list[str] = []

        def _scrape_one(url: str) -> str:
            try:
                tool = WebScraperTool(timeout=10)
                raw = tool._run(url)
                data = json.loads(raw)
                if "error" in data:
                    return ""
                desc = data.get("description", "")
                return desc[:500] if desc else ""
            except Exception:
                return ""

        with ThreadPoolExecutor(max_workers=min(len(urls), 3)) as executor:
            futures = {executor.submit(_scrape_one, u): u for u in urls}
            for future in as_completed(futures):
                url = futures[future]
                text = future.result()
                if text:
                    results.append(f"[{url}]: {text}")
                    console.print(f"[dim]  🌐 Scrapeado: {url[:60]}")

        return results

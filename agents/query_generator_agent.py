"""
agents/query_generator_agent.py — Generates search queries from BusinessSummary.

Responsibilities (T035):
  1. Take a BusinessSummary + SearchConfig.
  2. Use LLM to generate 10-20 diverse search queries.
  3. Combine with any manual queries from config.
  4. Deduplicate (case-insensitive).
"""

from __future__ import annotations

import json
import re

from langchain_core.language_models import BaseChatModel
from rich.console import Console

from models import BusinessSummary, SearchConfig
from prompts.query_generator_prompt import (
    QUERY_GENERATOR_HUMAN,
    QUERY_GENERATOR_SYSTEM,
)

console = Console()


class QueryGeneratorAgent:
    """Generates search queries from a BusinessSummary using LLM."""

    @classmethod
    def process(
        cls,
        summary: BusinessSummary,
        config: SearchConfig,
        llm: BaseChatModel,
    ) -> list[str]:
        console.print(
            "[cyan]  🔎 QueryGeneratorAgent: generando queries de búsqueda..."
        )

        messages = [
            {"role": "system", "content": QUERY_GENERATOR_SYSTEM},
            {
                "role": "user",
                "content": QUERY_GENERATOR_HUMAN.format(
                    core_offering=summary.core_offering or "(No disponible)",
                    target_sectors=", ".join(summary.target_sectors)
                    or "(No disponible)",
                    pain_points=", ".join(summary.key_pain_points) or "(No disponible)",
                    differentiators=", ".join(summary.differentiators)
                    or "(No disponible)",
                    ideal_customers="\n".join(
                        f"- {ic}" for ic in summary.ideal_customers
                    )
                    or "(No disponible)",
                    city=config.city,
                    country=config.country,
                    language=config.language,
                ),
            },
        ]

        generated: list[str] = []
        try:
            response = llm.invoke(messages)
            content = (
                response.content if hasattr(response, "content") else str(response)
            )
            # Extract JSON array from response
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                generated = json.loads(match.group())
        except Exception as exc:
            console.print(f"[yellow]  ⚠ QueryGeneratorAgent LLM fallback: {exc}")

        # Fallback: generate basic queries from ideal_customers if LLM failed
        if not generated and summary.ideal_customers:
            generated = [f"{ic} {config.city}" for ic in summary.ideal_customers[:10]]
            console.print("[yellow]  ⚠ Usando queries fallback desde ideal_customers")

        # Cap generated queries to avoid explosion in SearchAgent
        MAX_GENERATED = 15
        if len(generated) > MAX_GENERATED:
            generated = generated[:MAX_GENERATED]

        # Combine: manual queries first, then generated
        manual = list(config.queries)
        all_queries = _deduplicate(manual + generated)

        console.print(
            f"[green]  ✓ QueryGeneratorAgent: {len(all_queries)} queries "
            f"({len(manual)} manuales + {len(generated)} generadas)"
        )
        return all_queries


def _deduplicate(queries: list[str]) -> list[str]:
    """Case-insensitive deduplication preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for q in queries:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(q.strip())
    return result

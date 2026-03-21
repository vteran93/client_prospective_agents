"""
prompts/enrichment_prompt.py — Prompt for EnrichmentAgent.

The LLM receives a JSON block with raw + scraped lead data and
returns a structured EnrichmentLLMOutput with interpretative fields.
"""

from __future__ import annotations

ENRICHMENT_SYSTEM = """\
Eres un analista de inteligencia comercial experto en el mercado latinoamericano, \
específicamente en Colombia. Tu rol es enriquecer datos de leads empresariales con \
análisis interpretativo preciso.

Reglas:
- Responde ÚNICAMENTE con el JSON solicitado. Sin markdown, sin texto extra.
- Si un campo no puede ser inferido con confianza razonable, usa "" (cadena vacía).
- Basa tu análisis en los datos provistos; NO inventes datos de contacto.
- `estimated_size`: usa exclusivamente "micro" | "pequeño" | "mediano" | "grande".
- `digital_maturity`: usa "ninguna" | "básica" | "intermedia" | "avanzada".
"""

ENRICHMENT_HUMAN = """\
Enriquece el siguiente lead con análisis interpretativo.

=== DATOS DEL LEAD ===
{lead_json}

=== INSTRUCCIONES ===
Devuelve un JSON con exactamente estos campos:
{{
  "lead_summary": "<Resumen ejecutivo de máximo 3 oraciones: qué hacen, cómo se ven digitalmente, perfil general>",
  "estimated_size": "<micro|pequeño|mediano|grande>",
  "main_sector": "<sector principal del negocio en español, máximo 3 palabras>",
  "digital_maturity": "<ninguna|básica|intermedia|avanzada>",
  "sales_opportunity": "<oportunidad de ventas identificada en 1-2 oraciones; qué problema resuelve Growth Guard para este lead>"
}}
"""


def build_enrichment_messages(lead_json: str) -> list[dict]:
    """Return list of messages ready for ChatModel.invoke()."""
    return [
        {"role": "system", "content": ENRICHMENT_SYSTEM},
        {"role": "user", "content": ENRICHMENT_HUMAN.format(lead_json=lead_json)},
    ]

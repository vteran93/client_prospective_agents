"""
prompts/qualifier_prompt.py — Prompt for QualifierAgent.

Synthesises the enrichment + profiling data into a final score and tier.

Scoring formula (0-10 scale, each 0-10 sub-score):
  final_score = (
      hormozi_score       * 0.35  +   # market quality
      challenger_score    * 0.20  +   # sales approach fit
      digital_score       * 0.15  +   # digital maturity (inverted — lower = more opportunity)
      reviews_score       * 0.10  +   # social proof (normalised Google rating)
      cardone_score       * 0.20      # commitment level
  )

Tiers:
  HOT  → final_score >= 7.0
  WARM → final_score >= 4.5
  COLD → below 4.5
"""

from __future__ import annotations

QUALIFIER_SYSTEM = """\
Eres un experto en calificación de leads B2B con metodología basada en datos cuantitativos. \
Tu tarea es asignar un score final (0-10) a cada prospecto y clasificarlo en un tier \
(HOT / WARM / COLD) basado en la síntesis de todos los datos disponibles.

Fórmula de referencia:
  final_score = (hormozi_score/10 * 0.35 + challenger_factor * 0.20 + digital_factor * 0.15 + rating_factor * 0.10 + cardone_factor * 0.20) * 10

  - challenger_factor: mobilizer=1.0, unknown=0.6, talker=0.4, blocker=0.1
  - digital_factor: ninguna=1.0, básica=0.7, intermedia=0.4, avanzada=0.1 (más digital = menos oportunidad)
  - rating_factor: google_rating / 5.0
  - cardone_factor: high=1.0, medium=0.6, low=0.2

Tiers:
  HOT  → final_score >= 7.0
  WARM → 4.5 <= final_score < 7.0
  COLD → final_score < 4.5

Si un lead tiene razones claras para descartar (cerrado permanentemente, fuera de segmento, etc.),
indica discard_reason con el motivo.

Reglas:
- Responde ÚNICAMENTE con JSON válido. Sin markdown, sin texto extra.
- El score debe ser un número decimal con máximo 2 decimales.
"""

QUALIFIER_HUMAN = """\
Califica el siguiente prospecto y asigna su tier comercial.

=== DATOS COMPLETOS DEL PROSPECTO ===
{lead_json}

=== JSON ESPERADO ===
{{
  "final_score": <0.0-10.0>,
  "tier": "<HOT|WARM|COLD>",
  "contact_priority": <1-999, donde 1 es la máxima prioridad>,
  "discard_reason": "<razón si debe descartarse, null si no>"
}}
"""


def build_qualifier_messages(lead_json: str) -> list[dict]:
    """Return list of messages ready for ChatModel.invoke()."""
    return [
        {"role": "system", "content": QUALIFIER_SYSTEM},
        {"role": "user", "content": QUALIFIER_HUMAN.format(lead_json=lead_json)},
    ]

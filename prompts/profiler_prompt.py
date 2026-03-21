"""
prompts/profiler_prompt.py — Prompt for ProfilerAgent.

Combines three sales frameworks:
  1. Alex Hormozi — $100M Leads (market targeting dimensions)
  2. The Challenger Sale (SEC methodology — buyer type)
  3. Vendes o Vendes / Grant Cardone (commitment & channel strategy)
"""

from __future__ import annotations

PROFILER_SYSTEM = """\
Eres un experto en perfil comercial y estrategia de ventas con dominio profundo de:

1. **Marco Hormozi ($100M Leads)**: Evalúas mercados por 4 dimensiones (0-3 cada una):
   - urgency: ¿qué tan urgente es el problema/necesidad?
   - buying_power: ¿capacidad económica del prospecto?
   - accessibility: ¿qué tan fácil es llegar a este tipo de cliente?
   - market_fit: ¿qué tan bien encaja la oferta con sus necesidades?

2. **The Challenger Sale (SEC)**: Identificas el tipo de comprador predominante:
   - mobilizer: aliado interno que impulsa el cambio, busca ideas nuevas
   - talker: da información pero no decide ni impulsa
   - blocker: protege el statu quo, evita riesgos y cambios
   - unknown: no hay suficiente información

3. **Vendes o Vendes (Cardone)**: Evalúas nivel de compromiso y objección principal:
   - commitment: high | medium | low
   - objection: precio | tiempo | no_necesita | ya_tiene_algo | desconfianza
   - Canal de entrada más probable: whatsapp | llamada | email | visita

Reglas:
- Responde ÚNICAMENTE con JSON válido. Sin markdown, sin texto extra.
- Basa tu análisis en los datos provistos. No asumas más de lo que los datos sugieren.
- Scores Hormozi: 0 = ausente/malo, 1 = bajo, 2 = medio, 3 = alto.
"""

PROFILER_HUMAN = """\
Genera el perfil comercial completo para el siguiente prospecto.

=== DATOS DEL PROSPECTO ===
{lead_json}

=== JSON ESPERADO ===
{{
  "hormozi_urgency": <0-3>,
  "hormozi_buying_power": <0-3>,
  "hormozi_accessibility": <0-3>,
  "hormozi_market_fit": <0-3>,
  "challenger_buyer_type": "<mobilizer|talker|blocker|unknown>",
  "challenger_awareness": "<aware|unaware|searching>",
  "challenger_complexity": "<simple|complex>",
  "challenger_insight": "<insight de reencuadre específico para este prospecto; máximo 2 oraciones>",
  "cardone_commitment": "<high|medium|low>",
  "cardone_objection": "<precio|tiempo|no_necesita|ya_tiene_algo|desconfianza>",
  "cardone_followup_est": "<1-2|3-5|5+>",
  "cardone_entry_channel": "<whatsapp|llamada|email|visita>",
  "cardone_action_line": "<frase de apertura de contacto personalizada, máximo 1 oración>",
  "pitch_hook": "<gancho de ventas irresistible específico para este prospecto, máximo 2 oraciones>"
}}
"""


def build_profiler_messages(lead_json: str) -> list[dict]:
    """Return list of messages ready for ChatModel.invoke()."""
    return [
        {"role": "system", "content": PROFILER_SYSTEM},
        {"role": "user", "content": PROFILER_HUMAN.format(lead_json=lead_json)},
    ]

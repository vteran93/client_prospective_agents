"""
agents/qualifier_agent.py — LLM-powered lead qualifier.

Assigns a final_score (0-10), tier (HOT / WARM / COLD), contact_priority,
and optional discard_reason to each ProfiledLead.

Scoring formula (applied both deterministically and validated by LLM):
  final_score = (
      hormozi_score/10  * 0.35 +
      challenger_factor * 0.20 +
      digital_factor    * 0.15 +
      rating_factor     * 0.10 +
      cardone_factor    * 0.20
  ) * 10

Tiers:
  HOT  → final_score >= 7.0
  WARM → final_score >= 4.5
  COLD → below 4.5
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from models import ProfiledLead, QualifiedLead, QualificationConfig, QualifierLLMOutput
from prompts.qualifier_prompt import build_qualifier_messages

console = Console()

_CHALLENGER_FACTORS = {"mobilizer": 1.0, "unknown": 0.6, "talker": 0.4, "blocker": 0.1}
_DIGITAL_FACTORS = {"ninguna": 1.0, "básica": 0.7, "intermedia": 0.4, "avanzada": 0.1}
_CARDONE_FACTORS = {"high": 1.0, "medium": 0.6, "low": 0.2}


class QualifierAgent:
    """Final qualification step: scores + tiers each ProfiledLead."""

    @classmethod
    def process(
        cls,
        leads: Sequence[ProfiledLead],
        config,  # SearchConfig — typed loosely to avoid circular import
        llm: BaseChatModel,
    ) -> list[QualifiedLead]:
        qual_config: QualificationConfig = getattr(
            config, "qualification", QualificationConfig()
        )
        agent = cls(llm, qual_config)
        return agent.run(list(leads))

    def __init__(self, llm: BaseChatModel, qual_config: QualificationConfig) -> None:
        self.llm = llm
        self.qual_config = qual_config

    # ──────────────────────────────────────────────────────────────

    def run(self, leads: list[ProfiledLead]) -> list[QualifiedLead]:
        qualified: list[QualifiedLead] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Calificando leads...", total=len(leads))
            for lead in leads:
                ql = self._qualify_one(lead)
                qualified.append(ql)
                progress.advance(task_id)

        # Sort by final_score descending, assign contact_priority
        qualified.sort(key=lambda l: l.final_score, reverse=True)
        for idx, lead in enumerate(qualified, start=1):
            lead.contact_priority = idx

        hot = sum(1 for l in qualified if l.tier == "HOT")
        warm = sum(1 for l in qualified if l.tier == "WARM")
        cold = sum(1 for l in qualified if l.tier == "COLD")
        console.print(
            f"[green]  ✓ QualifierAgent: {hot} HOT · {warm} WARM · {cold} COLD"
        )
        return qualified

    # ──────────────────────────────────────────────────────────────

    def _qualify_one(self, lead: ProfiledLead) -> QualifiedLead:
        """Score + tier a single ProfiledLead."""
        # Deterministic score as a baseline
        det_score = _compute_score(lead)
        det_tier = _score_to_tier(det_score, self.qual_config)

        # Ask LLM to validate / refine (with context)
        lead_dict = {
            "name": lead.name,
            "sector": lead.main_sector,
            "digital_maturity": lead.digital_maturity,
            "rating": lead.rating,
            "has_whatsapp": lead.has_whatsapp,
            "hormozi_score": lead.profile.hormozi_score,
            "hormozi_label": lead.profile.hormozi_label,
            "challenger_buyer_type": lead.profile.challenger_buyer_type,
            "cardone_commitment": lead.profile.cardone_commitment,
            "cardone_objection": lead.profile.cardone_objection,
            "sales_opportunity": lead.sales_opportunity,
            "deterministic_score": round(det_score, 2),
            "deterministic_tier": det_tier,
        }

        final_score = det_score
        tier = det_tier
        discard_reason: str | None = None

        try:
            messages = build_qualifier_messages(
                json.dumps(lead_dict, ensure_ascii=False)
            )
            structured_llm = self.llm.with_structured_output(QualifierLLMOutput)
            result: QualifierLLMOutput = structured_llm.invoke(messages)
            final_score = float(result.final_score)
            tier = result.tier
            discard_reason = result.discard_reason or None
        except Exception:  # noqa: BLE001
            pass  # Keep deterministic values

        ql_data = lead.model_dump()
        ql_data["final_score"] = round(final_score, 2)
        ql_data["tier"] = tier
        ql_data["discard_reason"] = discard_reason
        ql_data["contact_priority"] = 999  # will be ranked after sort
        return QualifiedLead(**ql_data)


# ──────────────────────────────────────────────────────────────────
# Scoring helpers
# ──────────────────────────────────────────────────────────────────


def _compute_score(lead: ProfiledLead) -> float:
    p = lead.profile
    hormozi = (p.hormozi_score / 10.0) if p.hormozi_score else 0.0
    challenger = _CHALLENGER_FACTORS.get(p.challenger_buyer_type, 0.6)
    digital = _DIGITAL_FACTORS.get(lead.digital_maturity or "ninguna", 1.0)
    rating = (lead.rating / 5.0) if lead.rating else 0.0
    cardone = _CARDONE_FACTORS.get(p.cardone_commitment, 0.6)

    raw = (
        hormozi * 0.35
        + challenger * 0.20
        + digital * 0.15
        + rating * 0.10
        + cardone * 0.20
    ) * 10
    return round(min(10.0, max(0.0, raw)), 2)


def _score_to_tier(
    score: float,
    cfg: QualificationConfig,
) -> str:
    if score >= cfg.min_score_hot:
        return "HOT"
    if score >= cfg.min_score_warm:
        return "WARM"
    return "COLD"


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None

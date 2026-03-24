"""
models.py — Pydantic v2 data models for the prospecting pipeline.

Chain de herencia:
  RawLead → EnrichedLead → ProfiledLead → QualifiedLead
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────


class QualificationConfig(BaseModel):
    min_score_hot: float = 8.0
    min_score_warm: float = 5.0
    target_hot_warm: int = 80


class BusinessContext(BaseModel):
    """Contexto del negocio del usuario para auto-generación de queries (EP-7)."""

    description: str
    reference_urls: List[str] = Field(default_factory=list)
    target_audience: str = ""
    ideal_customers: List[str] = Field(default_factory=list)


class BusinessSummary(BaseModel):
    """Resumen estructurado generado por ContextAgent (T034)."""

    core_offering: str = ""
    target_sectors: List[str] = Field(default_factory=list)
    key_pain_points: List[str] = Field(default_factory=list)
    differentiators: List[str] = Field(default_factory=list)
    geographic_focus: str = ""
    ideal_customers: List[str] = Field(default_factory=list)
    raw_context: str = Field(default="", max_length=3000)


class QueryList(BaseModel):
    """Lista estructurada de queries generadas por QueryGeneratorAgent (T035)."""

    queries: List[str] = Field(default_factory=list)


class SearchConfig(BaseModel):
    campaign_name: str
    queries: List[str] = Field(default_factory=list)
    city: str
    country: str = "Colombia"
    language: str = "es"
    max_leads: int = Field(gt=0, default=150)
    max_iterations: int = Field(default=3, ge=1, le=20)
    sources: List[str] = Field(default_factory=lambda: ["duckduckgo"])
    scrape_websites: bool = True
    scraper_concurrency: int = Field(default=8, ge=1, le=50)
    output_filename: str = "prospectos"
    llm_provider: str = "bedrock"
    qualification: QualificationConfig = Field(default_factory=QualificationConfig)
    business_context: Optional[BusinessContext] = None

    @model_validator(mode="after")
    def validate_queries_or_business_context(self) -> "SearchConfig":
        if not self.queries and not self.business_context:
            raise ValueError(
                "Se requiere 'queries' o 'business_context' (al menos uno)"
            )
        return self


# ──────────────────────────────────────────────────────────────────
# Raw lead (after Search + Maps)
# ──────────────────────────────────────────────────────────────────


class RawLead(BaseModel):
    source: str  # "google_maps" | "tavily" | "brave" | "duckduckgo"
    name: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    rating: float = 0.0
    reviews_count: int = 0
    lat: float = 0.0
    lng: float = 0.0
    social_links: Dict[str, str] = Field(default_factory=dict)
    raw_snippet: str = ""
    place_id: str = ""
    opening_hours: Dict[str, List[str]] = Field(default_factory=dict)
    popular_times: List[Dict[str, Any]] = Field(default_factory=list)
    timezone: str = "America/Bogota"
    business_status: str = "OPERATIONAL"


# ──────────────────────────────────────────────────────────────────
# Scraped profile (intermediate, merged into EnrichedLead)
# ──────────────────────────────────────────────────────────────────


class ScrapedProfile(BaseModel):
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    has_whatsapp: bool = False
    whatsapp_number: str = ""
    social_links: Dict[str, str] = Field(default_factory=dict)
    description: str = ""
    technology_stack: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# Enriched lead (after Scraper + EnrichmentAgent)
# ──────────────────────────────────────────────────────────────────


class EnrichedLead(RawLead):
    emails_scraped: List[str] = Field(default_factory=list)
    phones_scraped: List[str] = Field(default_factory=list)
    has_whatsapp: bool = False
    whatsapp_number: str = ""
    technology_stack: List[str] = Field(default_factory=list)
    lead_summary: str = ""
    estimated_size: str = ""  # micro | pequeño | mediano
    main_sector: str = ""
    digital_maturity: str = ""  # ninguna | básica | intermedia | avanzada
    sales_opportunity: str = ""
    merge_sources: List[str] = Field(default_factory=list)
    scrape_failed: bool = False


# ──────────────────────────────────────────────────────────────────
# Commercial profile (output of ProfilerAgent)
# ──────────────────────────────────────────────────────────────────


class CommercialProfile(BaseModel):
    # ── Hormozi ───────────────────────────────────────────────────
    hormozi_urgency: int = Field(default=0, ge=0, le=3)
    hormozi_buying_power: int = Field(default=0, ge=0, le=3)
    hormozi_accessibility: int = Field(default=0, ge=0, le=3)
    hormozi_market_fit: int = Field(default=0, ge=0, le=3)
    hormozi_score: float = Field(default=0.0)
    hormozi_label: str = Field(
        default="COLD_MARKET"
    )  # STARVING_CROWD|WARM_MARKET|COLD_MARKET

    # ── Challenger ────────────────────────────────────────────────
    challenger_buyer_type: str = "unknown"  # mobilizer|talker|blocker|unknown
    challenger_awareness: str = "unaware"  # aware|unaware|searching
    challenger_complexity: str = "simple"  # simple|complex
    challenger_insight: str = ""

    # ── Cardone ───────────────────────────────────────────────────
    cardone_commitment: str = "low"  # high|medium|low
    cardone_objection: str = (
        "desconfianza"  # precio|tiempo|no_necesita|ya_tiene_algo|desconfianza
    )
    cardone_followup_est: str = "3-5"  # 1-2|3-5|5+
    cardone_entry_channel: str = "whatsapp"  # whatsapp|llamada|email|visita
    cardone_action_line: str = ""

    # ── Composite ─────────────────────────────────────────────────
    composite_profile_score: float = 0.0
    pitch_hook: str = ""

    @model_validator(mode="after")
    def compute_hormozi_derived(self) -> "CommercialProfile":
        raw = (
            self.hormozi_urgency
            + self.hormozi_buying_power
            + self.hormozi_accessibility
            + self.hormozi_market_fit
        )
        self.hormozi_score = round(raw * (10.0 / 12.0), 2)
        if self.hormozi_score >= 8:
            self.hormozi_label = "STARVING_CROWD"
        elif self.hormozi_score >= 5:
            self.hormozi_label = "WARM_MARKET"
        else:
            self.hormozi_label = "COLD_MARKET"
        return self


# ──────────────────────────────────────────────────────────────────
# Visit timing (output of VisitTimingAgent)
# ──────────────────────────────────────────────────────────────────


class VisitTiming(BaseModel):
    """Best visit/call windows determined by VisitTimingAgent.
    Windows are plain dicts to remain flexible with LLM output shapes.
    Expected visit window keys: {day, start_hour, end_hour, reason}.
    Expected call time keys:    {day, hour, reason}.
    """

    best_visit_windows: List[Dict[str, Any]] = Field(default_factory=list)
    best_call_time: Dict[str, Any] = Field(default_factory=dict)
    worst_times: List[Dict[str, Any]] = Field(default_factory=list)
    timing_confidence: Literal["high", "inferred"] = "inferred"
    timing_summary: str = ""


# ──────────────────────────────────────────────────────────────────
# Profiled lead (after Profiler + VisitTiming agents)
# ──────────────────────────────────────────────────────────────────


class ProfiledLead(EnrichedLead):
    profile: CommercialProfile = Field(default_factory=CommercialProfile)
    visit_timing: VisitTiming = Field(default_factory=VisitTiming)


# ──────────────────────────────────────────────────────────────────
# Qualified lead (final output)
# ──────────────────────────────────────────────────────────────────


class QualifiedLead(ProfiledLead):
    final_score: float = 0.0
    tier: Literal["HOT", "WARM", "COLD"] = "COLD"
    discard_reason: Optional[str] = None
    contact_priority: int = 999


# ──────────────────────────────────────────────────────────────────
# Run report
# ──────────────────────────────────────────────────────────────────


class RunReport(BaseModel):
    campaign_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_raw: int = 0
    total_after_dedup: int = 0
    hot_count: int = 0
    warm_count: int = 0
    cold_count: int = 0
    sources_breakdown: Dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    iterations: int = 1
    leads_per_iteration: List[int] = Field(default_factory=list)
    error_log: List[Dict[str, str]] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# LLM structured output schemas (used by prompts/ modules)
# These are the fields the LLM must fill; computed fields are excluded.
# ──────────────────────────────────────────────────────────────────


class EnrichmentLLMOutput(BaseModel):
    lead_summary: str = Field(
        description="2 líneas: qué hace el negocio y qué lo distingue"
    )
    estimated_size: Literal["micro", "pequeño", "mediano"] = Field(
        description="micro=1-5 empleados, pequeño=5-20, mediano=20-100"
    )
    main_sector: str = Field(description="sector principal del negocio")
    digital_maturity: Literal["ninguna", "básica", "intermedia", "avanzada"] = Field(
        description="nivel de presencia digital del negocio"
    )
    sales_opportunity: str = Field(
        description="1 línea: por qué Growth Guard les sirve específicamente"
    )


class ProfilerLLMOutput(BaseModel):
    """Campos que llena el LLM — scores Hormozi + perfiles Challenger y Cardone."""

    # Hormozi (el score y label se calculan en CommercialProfile.model_validator)
    hormozi_urgency: int = Field(
        ge=0, le=3, description="Urgencia del dolor: 0=ninguna, 3=crítica"
    )
    hormozi_buying_power: int = Field(
        ge=0, le=3, description="Capacidad de pago estimada"
    )
    hormozi_accessibility: int = Field(
        ge=0, le=3, description="Contactabilidad verificada"
    )
    hormozi_market_fit: int = Field(ge=0, le=3, description="Fit con Growth Guard")

    # Challenger
    challenger_buyer_type: Literal["mobilizer", "talker", "blocker", "unknown"]
    challenger_awareness: Literal["aware", "unaware", "searching"]
    challenger_complexity: Literal["simple", "complex"]
    challenger_insight: str = Field(
        description="Insight específico para reencuadrar la conversación"
    )

    # Cardone
    cardone_commitment: Literal["high", "medium", "low"]
    cardone_objection: Literal[
        "precio", "tiempo", "no_necesita", "ya_tiene_algo", "desconfianza"
    ]
    cardone_followup_est: Literal["1-2", "3-5", "5+"]
    cardone_entry_channel: Literal["whatsapp", "llamada", "email", "visita"]
    cardone_action_line: str = Field(
        description="Primera acción recomendada para el vendedor"
    )

    # Composite
    composite_profile_score: float = Field(ge=0, le=10)
    pitch_hook: str = Field(
        description="Primer mensaje personalizado, máximo 2 oraciones"
    )


class TimingLLMOutput(BaseModel):
    best_visit_windows: List[Dict[str, Any]] = Field(
        description="Lista de ventanas: [{day, time_start, time_end, busyness_pct, reason}]"
    )
    best_call_time: Dict[str, str] = Field(description="{day, time, reason}")
    worst_times: List[Dict[str, Any]] = Field(description="[{day, time_range, reason}]")
    timing_confidence: Literal["high", "inferred"]
    timing_summary: str = Field(
        description="1 línea accionable: ej. 'Visitar martes 10-11:30. Evitar sábados.'"
    )


class QualifierLLMOutput(BaseModel):
    final_score: float = Field(ge=0.0, le=10.0)
    tier: Literal["HOT", "WARM", "COLD"]
    contact_priority: int = Field(default=999, ge=1)
    discard_reason: Optional[str] = Field(
        default=None, description="Solo si tier=COLD: razón de descarte en 1 línea"
    )

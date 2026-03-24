"""
config.py — Config loader and AppSettings.

Uso:
    settings = AppSettings()
    config = load_config("search_config.yaml")
    validate_api_keys(config, settings)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from models import BusinessContext, QualificationConfig, SearchConfig


# ──────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────


class ConfigError(Exception):
    """Raised when a required configuration value is missing or invalid."""


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM — Bedrock
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_default_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    # LLM — OpenAI
    openai_api_key: Optional[str] = None

    # Search APIs
    tavily_api_key: Optional[str] = None
    brave_api_key: Optional[str] = None
    searxng_base_url: Optional[str] = None

    # Maps
    google_maps_api_key: Optional[str] = None

    # Runtime overrides
    llm_provider: str = "bedrock"
    llm_temperature: float = 0.2


# ──────────────────────────────────────────────────────────────────
# Config loader
# ──────────────────────────────────────────────────────────────────


def load_config(path: str, overrides: Optional[dict] = None) -> SearchConfig:
    """
    Load and validate SearchConfig from a YAML file.

    Args:
        path: Path to search_config.yaml
        overrides: Optional dict of field overrides (from CLI args)

    Returns:
        Validated SearchConfig instance

    Raises:
        ConfigError: If the file does not exist or YAML is malformed
    """
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise ConfigError(f"Archivo de configuración no encontrado: {path}")

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido en {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"El archivo {path} debe ser un dict YAML válido")

    campaign = raw.get("campaign", {})
    llm_section = raw.get("llm", {})
    qual_section = raw.get("qualification", {})
    bc_section = campaign.get("business_context")

    data: dict = {
        "campaign_name": campaign.get("name", "unnamed_campaign"),
        "queries": campaign.get("queries", []),
        "city": campaign.get("city", ""),
        "country": campaign.get("country", "Colombia"),
        "language": campaign.get("language", "es"),
        "max_leads": campaign.get("max_leads", 150),
        "max_iterations": campaign.get("max_iterations", 3),
        "sources": campaign.get("sources", ["duckduckgo"]),
        "scrape_websites": campaign.get("scrape_websites", True),
        "scraper_concurrency": campaign.get("scraper_concurrency", 8),
        "output_filename": campaign.get("output_filename", "prospectos"),
        "llm_provider": llm_section.get("provider", "bedrock"),
        "qualification": QualificationConfig(
            min_score_hot=qual_section.get("min_score_hot", 8.0),
            min_score_warm=qual_section.get("min_score_warm", 5.0),
            target_hot_warm=qual_section.get("target_hot_warm", 80),
        ),
    }

    if bc_section and isinstance(bc_section, dict):
        data["business_context"] = BusinessContext(
            description=bc_section.get("description", ""),
            reference_urls=bc_section.get("reference_urls", []),
            target_audience=bc_section.get("target_audience", ""),
            ideal_customers=bc_section.get("ideal_customers", []),
        )

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                data[key] = value

    try:
        return SearchConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Config inválida: {exc}") from exc


# ──────────────────────────────────────────────────────────────────
# API key validator
# ──────────────────────────────────────────────────────────────────

_SOURCE_KEY_MAP: dict = {
    "tavily": ("tavily_api_key", "TAVILY_API_KEY"),
    "brave": ("brave_api_key", "BRAVE_API_KEY"),
    "google_maps": ("google_maps_api_key", "GOOGLE_MAPS_API_KEY"),
}

_LLM_KEY_MAP: dict = {
    "bedrock": [
        ("aws_access_key_id", "AWS_ACCESS_KEY_ID"),
        ("aws_secret_access_key", "AWS_SECRET_ACCESS_KEY"),
    ],
    "openai": [("openai_api_key", "OPENAI_API_KEY")],
}


def validate_api_keys(config: SearchConfig, settings: AppSettings) -> None:
    """
    Verify all required API keys are present given the active sources and LLM.

    Raises:
        ConfigError: with a human-readable message listing every missing key
    """
    errors: list[str] = []

    for source in config.sources:
        if source in _SOURCE_KEY_MAP:
            attr, env_var = _SOURCE_KEY_MAP[source]
            if not getattr(settings, attr):
                errors.append(f"{env_var} requerida para source='{source}'")

    provider = config.llm_provider
    if provider in _LLM_KEY_MAP:
        for attr, env_var in _LLM_KEY_MAP[provider]:
            if not getattr(settings, attr):
                errors.append(f"{env_var} requerida para llm.provider='{provider}'")

    if errors:
        raise ConfigError(
            "Faltan variables de entorno requeridas:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

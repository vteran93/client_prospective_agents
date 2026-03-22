"""
tests/test_config.py — Unit tests for config.py loader.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config import ConfigError, load_config


_FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadConfig:
    def test_smoke_config_loads(self):
        cfg = load_config(str(_FIXTURES / "smoke_config.yaml"))
        assert cfg.campaign_name == "Smoke Test Campaign"
        assert cfg.city == "Bogotá"
        assert "duckduckgo" in cfg.sources
        assert cfg.qualification.min_score_hot == 7.0

    def test_missing_file_raises(self):
        with pytest.raises(ConfigError, match="no encontrado"):
            load_config("nonexistent.yaml")

    def test_overrides_applied(self):
        cfg = load_config(
            str(_FIXTURES / "smoke_config.yaml"),
            overrides={"max_leads": 42, "llm_provider": "openai"},
        )
        assert cfg.max_leads == 42
        assert cfg.llm_provider == "openai"

    def test_scrape_websites_default(self):
        cfg = load_config(str(_FIXTURES / "smoke_config.yaml"))
        assert cfg.scrape_websites is False  # smoke_config sets this


class TestValidateApiKeys:
    def test_duckduckgo_no_key_required(self):
        """DuckDuckGo source should not require any API key."""
        from config import AppSettings, validate_api_keys

        cfg = load_config(str(_FIXTURES / "smoke_config.yaml"))
        settings = AppSettings(
            aws_access_key_id=None,
            aws_secret_access_key=None,
            openai_api_key="sk-test",
        )
        # Should not raise
        validate_api_keys(cfg, settings)

    def test_missing_openai_key_raises(self):
        from config import AppSettings, validate_api_keys

        cfg = load_config(
            str(_FIXTURES / "smoke_config.yaml"),
            overrides={"llm_provider": "openai"},
        )
        settings = AppSettings(openai_api_key=None)
        with pytest.raises(ConfigError):
            validate_api_keys(cfg, settings)


class TestBusinessContextConfig:
    def test_load_business_context_from_yaml(self):
        cfg = load_config(str(_FIXTURES / "business_context_config.yaml"))
        assert cfg.campaign_name == "Business Context Only Campaign"
        assert cfg.queries == []
        assert cfg.business_context is not None
        assert (
            cfg.business_context.description
            == "Empresa de consultoría de ventas para PYMEs en Colombia"
        )
        assert len(cfg.business_context.reference_urls) == 1
        assert (
            cfg.business_context.target_audience
            == "Dueños y gerentes de PYMEs de servicios en Bogotá"
        )
        assert len(cfg.business_context.ideal_customers) == 2

    def test_smoke_config_no_business_context(self):
        """Retrocompatibilidad: config sin business_context sigue funcionando."""
        cfg = load_config(str(_FIXTURES / "smoke_config.yaml"))
        assert cfg.business_context is None
        assert len(cfg.queries) > 0

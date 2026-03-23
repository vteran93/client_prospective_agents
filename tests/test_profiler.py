"""
tests/test_profiler.py — Unit tests for ProfilerAgent seller context injection.

Tests:
  - build_profiler_messages includes seller_context in prompt
  - _build_seller_context formats BusinessContext correctly
  - ProfilerAgent.process passes business_context through to prompt
  - pitch_hook is generated with seller awareness
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import BusinessContext


# ── _build_seller_context ─────────────────────────────────────────

class TestBuildSellerContext:
    def test_none_returns_empty(self):
        from agents.profiler_agent import _build_seller_context

        assert _build_seller_context(None) == ""

    def test_description_only(self):
        from agents.profiler_agent import _build_seller_context

        bc = BusinessContext(description="Software de nómina para Colombia")
        result = _build_seller_context(bc)
        assert "Software de nómina para Colombia" in result

    def test_includes_target_audience(self):
        from agents.profiler_agent import _build_seller_context

        bc = BusinessContext(
            description="Software de nómina",
            target_audience="Gerentes de RRHH",
        )
        result = _build_seller_context(bc)
        assert "Audiencia objetivo: Gerentes de RRHH" in result

    def test_includes_ideal_customers(self):
        from agents.profiler_agent import _build_seller_context

        bc = BusinessContext(
            description="Consultoría",
            ideal_customers=["Constructoras", "Distribuidoras", "Hoteles"],
        )
        result = _build_seller_context(bc)
        assert "Clientes ideales:" in result
        assert "Constructoras" in result
        assert "Distribuidoras" in result

    def test_caps_ideal_customers_at_5(self):
        from agents.profiler_agent import _build_seller_context

        bc = BusinessContext(
            description="Consultoría",
            ideal_customers=[f"Cliente {i}" for i in range(10)],
        )
        result = _build_seller_context(bc)
        assert "Cliente 4" in result
        assert "Cliente 5" not in result


# ── build_profiler_messages ───────────────────────────────────────

class TestBuildProfilerMessages:
    def test_default_no_seller_context(self):
        from prompts.profiler_prompt import build_profiler_messages

        msgs = build_profiler_messages('{"name": "Test Lead"}')
        assert len(msgs) == 2
        assert "(No disponible)" in msgs[1]["content"]

    def test_with_seller_context(self):
        from prompts.profiler_prompt import build_profiler_messages

        msgs = build_profiler_messages(
            '{"name": "Test Lead"}',
            seller_context="Software de nómina SAIREH",
        )
        assert "Software de nómina SAIREH" in msgs[1]["content"]
        assert "DATOS DEL PROSPECTO" in msgs[1]["content"]

    def test_system_prompt_mentions_seller(self):
        from prompts.profiler_prompt import build_profiler_messages

        msgs = build_profiler_messages('{}')
        system = msgs[0]["content"]
        assert "servicio/producto" in system or "vendedor" in system


# ── ProfilerAgent with business_context ───────────────────────────

class TestProfilerAgentSellerContext:
    def test_process_without_business_context(self):
        """Should work without business_context (backward compatible)."""
        from agents.profiler_agent import ProfilerAgent
        from models import EnrichedLead, ProfilerLLMOutput

        lead = EnrichedLead(
            source="duckduckgo",
            name="Test Corp",
            lead_summary="Empresa de construcción",
        )

        mock_llm = MagicMock()
        output = ProfilerLLMOutput(
            hormozi_urgency=2,
            hormozi_buying_power=2,
            hormozi_accessibility=2,
            hormozi_market_fit=2,
            challenger_buyer_type="mobilizer",
            challenger_awareness="aware",
            challenger_complexity="simple",
            challenger_insight="Test insight",
            cardone_commitment="medium",
            cardone_objection="precio",
            cardone_followup_est="3-5",
            cardone_entry_channel="whatsapp",
            cardone_action_line="Hola, le contacto para...",
            composite_profile_score=7.0,
            pitch_hook="Le ayudamos a mejorar su operación",
        )
        structured = MagicMock()
        structured.invoke.return_value = output
        mock_llm.with_structured_output.return_value = structured

        result = ProfilerAgent.process([lead], mock_llm)
        assert len(result) == 1
        assert result[0].profile.pitch_hook == "Le ayudamos a mejorar su operación"

    @patch("agents.profiler_agent.build_profiler_messages")
    def test_process_passes_seller_context(self, mock_build):
        """When business_context is provided, seller_context reaches the prompt."""
        from agents.profiler_agent import ProfilerAgent
        from models import EnrichedLead, ProfilerLLMOutput

        mock_build.return_value = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
        ]

        lead = EnrichedLead(
            source="duckduckgo",
            name="Test Corp",
        )
        bc = BusinessContext(
            description="SAIREH software de nómina",
            target_audience="Gerentes de RRHH",
        )

        mock_llm = MagicMock()
        output = ProfilerLLMOutput(
            hormozi_urgency=1,
            hormozi_buying_power=1,
            hormozi_accessibility=1,
            hormozi_market_fit=1,
            challenger_buyer_type="unknown",
            challenger_awareness="unaware",
            challenger_complexity="simple",
            challenger_insight="",
            cardone_commitment="low",
            cardone_objection="desconfianza",
            cardone_followup_est="3-5",
            cardone_entry_channel="email",
            cardone_action_line="",
            composite_profile_score=3.0,
            pitch_hook="hook",
        )
        structured = MagicMock()
        structured.invoke.return_value = output
        mock_llm.with_structured_output.return_value = structured

        ProfilerAgent.process([lead], mock_llm, business_context=bc)

        # Verify build_profiler_messages was called with seller_context
        call_args = mock_build.call_args
        assert "seller_context" in call_args.kwargs or len(call_args.args) > 1
        seller_ctx = call_args.kwargs.get("seller_context", call_args.args[1] if len(call_args.args) > 1 else "")
        assert "SAIREH software de nómina" in seller_ctx
        assert "Audiencia objetivo: Gerentes de RRHH" in seller_ctx

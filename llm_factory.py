"""
llm_factory.py — LLM provider factory with Bedrock primary + OpenAI fallback.
"""

from __future__ import annotations

import time
from typing import Optional

from langchain_core.language_models import BaseChatModel
from rich.console import Console

from config import AppSettings

console = Console()

_MAX_RETRIES = 2
_BACKOFF_BASE = 1.5  # seconds


def get_llm(
    settings: AppSettings,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
) -> BaseChatModel:
    """
    Return the appropriate LLM based on provider or settings.llm_provider.
    Falls back to OpenAI if Bedrock is unavailable.

    Args:
        settings: AppSettings instance with credentials
        temperature: Override temperature (defaults to settings.llm_temperature)
        provider: Explicit provider override ("bedrock" | "openai"). Takes
                  precedence over settings.llm_provider when supplied.

    Returns:
        Configured BaseChatModel (ChatBedrock or ChatOpenAI)

    Raises:
        RuntimeError: If no LLM can be initialised with the given credentials
    """
    temp = temperature if temperature is not None else settings.llm_temperature
    effective_provider = provider or settings.llm_provider

    if effective_provider == "bedrock":
        llm = _build_bedrock(settings, temp)
        if llm is not None:
            return llm
        console.print("[yellow]⚠ Bedrock no disponible, usando OpenAI como fallback...")

    llm = _build_openai(settings, temp)
    if llm is not None:
        return llm

    raise RuntimeError(
        "No se pudo inicializar ningún LLM. "
        "Verifica AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY o OPENAI_API_KEY en .env"
    )


# ──────────────────────────────────────────────────────────────────
# Private builders
# ──────────────────────────────────────────────────────────────────


def _build_bedrock(
    settings: AppSettings, temperature: float
) -> Optional[BaseChatModel]:
    """Attempt to build a ChatBedrock instance; return None on any error."""
    try:
        from langchain_aws import ChatBedrock
        import boto3

        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_default_region,
        )
        client = session.client("bedrock-runtime")

        llm = ChatBedrock(
            client=client,
            model=settings.bedrock_model_id,  # langchain-aws >= 0.2
            model_kwargs={"temperature": temperature, "max_tokens": 4096},
        )
        console.print(f"[green]✓ LLM: Bedrock [{settings.bedrock_model_id}]")
        return llm

    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗ Bedrock init error: {exc}")
        return None


def _build_openai(settings: AppSettings, temperature: float) -> Optional[BaseChatModel]:
    """Attempt to build a ChatOpenAI instance; return None on any error."""
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model="gpt-4o",
            temperature=temperature,
            max_tokens=4096,  # type: ignore[call-arg]
        )
        console.print("[green]✓ LLM: OpenAI [gpt-4o]")
        return llm

    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗ OpenAI init error: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────
# Retry wrapper (used by agents for resilient LLM calls)
# ──────────────────────────────────────────────────────────────────


def llm_invoke_with_retry(
    llm: BaseChatModel, prompt, settings: AppSettings, provider: Optional[str] = None
):
    """
    Invoke LLM with automatic retry and Bedrock→OpenAI fallback on throttling.

    Args:
        llm: Current LLM instance
        prompt: LangChain runnable input (str, list of messages, etc.)
        settings: AppSettings for building fallback

    Returns:
        LLM response object
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            is_throttle = any(
                kw in str(exc).lower()
                for kw in ("throttling", "rate", "too many requests", "429", "503")
            )
            if is_throttle and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** (attempt + 1)
                console.print(
                    f"[yellow]⏳ LLM throttled, reintentando en {wait:.1f}s..."
                )
                time.sleep(wait)
            else:
                break

    # Final fallback: switch provider
    effective_provider = provider or settings.llm_provider
    if effective_provider == "bedrock":
        console.print("[yellow]↩ Activando fallback a OpenAI tras fallo en Bedrock...")
        fallback = _build_openai(settings, settings.llm_temperature)
        if fallback:
            return fallback.invoke(prompt)

    raise RuntimeError(f"LLM invoke failed after retries: {last_exc}") from last_exc

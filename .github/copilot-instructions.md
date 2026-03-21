# Copilot Instructions — Growth Guard Lead Prospecting Agents

## Contexto del proyecto

Sistema multi-agente de prospección B2B para Growth Guard (Colombia). Pipeline:
**Búsqueda web + Google Maps → Scraping → Dedup + Enriquecimiento LLM → Perfilización (Hormozi + Challenger + Cardone) → Calificación → Excel**

**Lee `AGENTS.md` en la raíz para el contexto completo antes de modificar cualquier archivo.**

---

## Convenciones críticas

### Python
- **Python 3.10** — sin syntax de 3.11+ (`match`, `ExceptionGroup`, etc.)
- **Pydantic v2** — usar `model_validator(mode="after")`, `Field(default_factory=...)`, NO sintaxis v1
- **pydantic-settings v2** — `SettingsConfigDict`, NO `class Config`
- **f-strings** para todo — no `.format()` ni `%`
- Imports ordenados: stdlib → third-party → local (con línea en blanco entre grupos)

### Modelos de datos
- La cadena es: `RawLead → EnrichedLead → ProfiledLead → QualifiedLead`
- **`VisitTiming`** usa `List[Dict[str, Any]]` para `best_visit_windows` y `worst_times` — NO sub-modelos Pydantic
- **`CommercialProfile.hormozi_score`** es siempre calculado por `@model_validator` — nunca lo setees manualmente
- Los modelos LLM (`EnrichmentLLMOutput`, `ProfilerLLMOutput`, etc.) son schemas separados para `with_structured_output()`

### Tools
- `tools/__init__.py` **debe permanecer vacío** — los imports de crewai a nivel de módulo rompen los tests
- `scraper_tool.py` tiene import condicional de `BaseTool` — no lo cambies a import directo
- `dedup_tool.py` y `excel_tool.py` **no tienen** dependencia de crewai — mantenlo así

### LLM factory
- `ChatBedrock` usa `model=` (no `model_id=`) — langchain-aws >= 0.2
- `max_tokens` va dentro de `model_kwargs` para Bedrock

### Configuración
- Los mensajes de error en `config.py` están en **español** — los tests lo esperan así
- `load_config(path, overrides)` — `overrides` es `dict`, no vars de entorno

---

## Tests

```bash
# Todos los tests unitarios (sin crewai instalado)
python -m pytest tests/ -q

# Solo un módulo
python -m pytest tests/test_models.py -v
```

**55/55 tests deben pasar siempre.** Al agregar features, añade tests.

Tests pendientes: `test_excel_tool.py`, tests de integración de agentes.

---

## Setup rápido en WSL

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install pydantic>=2.0 pydantic-settings>=2.0 pyyaml rapidfuzz unidecode \
    httpx beautifulsoup4 pytest
# Para producción completa:
pip install crewai>=0.80 langchain-aws>=0.2 langchain-openai>=0.2 \
    langchain-core boto3 tavily-python duckduckgo-search playwright openpyxl rich
playwright install chromium
```

---

## Lo que FALTA por implementar (al 2026-03-21)

| Prioridad | Tarea |
|-----------|-------|
| P0 | `tests/test_excel_tool.py` — validar Excel E2E con 20 leads |
| P1 | Tests integración agentes con LLM mockeado |
| P1 | Smoke test: `python main.py --config tests/fixtures/smoke_config.yaml --max-leads 5` |
| P2 | `output_agent.py` — generar `run_log_{timestamp}.json` |
| P2 | README para el equipo de ventas |

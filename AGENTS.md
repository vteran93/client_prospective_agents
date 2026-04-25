# AGENTS.md — Contexto completo del proyecto para IA (Claude / Copilot)

> **Propósito**: Este archivo es el volcado de memoria del sistema de IA que construyó el proyecto.
> Léelo completo antes de hacer cualquier modificación al código.  
> **Última actualización**: 2026-03-21

---

## 1. ¿Qué es este proyecto?

Sistema multi-agente de prospección de leads B2B para **Growth Guard** (empresa colombiana de consultoría de ventas). Dada una campaña configurada en YAML, el sistema:

1. Busca negocios en Bogotá/Colombia usando Tavily, Brave, DuckDuckGo y Google Maps
2. Hace scraping de sus sitios web
3. Deduplica y enriquece los leads con LLM
4. Perfila a cada decisor usando 3 frameworks de ventas: **Hormozi**, **El Vendedor Desafiante (CEB)**, **Grant Cardone**
5. Analiza los mejores horarios de visita/llamada (popular_times de Google Maps)
6. Califica y ordena los leads (HOT/WARM/COLD)
7. Exporta todo a **Excel** con 5 hojas y formato visual + colores por tier

**Comando de ejecución:**
```bash
python main.py --config search_config.yaml --max-leads 30 --llm openai
```

---

## 2. Stack técnico

| Capa | Tecnología | Notas |
|------|-----------|-------|
| Python | **3.10** | Path WSL: `python3.10` |
| LLM primario | AWS Bedrock `anthropic.claude-3-5-sonnet-20241022-v2:0` | via `langchain-aws` `ChatBedrock` |
| LLM fallback | OpenAI `gpt-4o` | via `langchain-openai` `ChatOpenAI` |
| Agentes | **CrewAI** (`BaseTool`) | Solo se usa `BaseTool` — NO `Process.hierarchical` |
| Flujo | Python programático híbrido en `crew.py` | `ThreadPoolExecutor` para paralelismo |
| Search | Tavily + Brave + DuckDuckGo | DuckDuckGo = modo dev sin API key |
| Maps | Google Places API (New) v1 | POST `/places:searchText` + GET `/places/{id}` |
| Popular times | Playwright scraping de Google Maps | La API no expone estos datos |
| Scraping | `httpx` + `BeautifulSoup4` estático, Playwright fallback | Heurística por `_JS_SIGNALS` |
| Dedup | `rapidfuzz` `token_sort_ratio >= 85` | + exact `place_id` + phone 7-prefix |
| Output | `openpyxl` Excel | 5 hojas + color coding |
| Modelos | Pydantic v2 | `pydantic-settings` v2 para `.env` |
| CLI | `argparse` + `rich` | |
| Tests | `pytest` | **55/55 pasando** |

---

## 3. Estructura de archivos

```
client_prospective_agents/
│
├── main.py               # CLI entry point (argparse + rich banner)
├── crew.py               # ProspectingCrew — orquestador principal
├── config.py             # load_config() + AppSettings (pydantic-settings)
├── llm_factory.py        # get_llm() — Bedrock primary + OpenAI fallback + retry
├── models.py             # TODOS los modelos Pydantic v2 (fuente única de verdad)
│
├── search_config.yaml    # Configuración de campaña de ejemplo (Talleres Bogotá)
├── requirements.txt      # Dependencias pinneadas
├── .env.example          # Template de variables de entorno
├── .gitignore
│
├── agents/
│   ├── __init__.py
│   ├── search_agent.py       # LLM query expansion + multi-source web search
│   ├── maps_agent.py         # Google Places textsearch + place details
│   ├── scraper_agent.py      # ThreadPoolExecutor concurrent website scraping
│   ├── enrichment_agent.py   # Dedup + LLM enrichment
│   ├── visit_timing_agent.py # Playwright popular_times prefetch + LLM timing
│   ├── profiler_agent.py     # CommercialProfile generation (3 frameworks)
│   ├── qualifier_agent.py    # Deterministic score + LLM-validated tier
│   └── output_agent.py       # Excel export + Rich console summary
│
├── tools/
│   ├── __init__.py           # VACÍO — imports condicionales en cada archivo
│   ├── tavily_tool.py        # TavilySearchTool (BaseTool)
│   ├── brave_tool.py         # BraveSearchTool (BaseTool)
│   ├── duckduckgo_tool.py    # DuckDuckGoSearchTool (BaseTool)
│   ├── maps_tool.py          # GoogleMapsSearchTool + GoogleMapsDetailsTool
│   ├── popular_times_tool.py # PopularTimesTool — Playwright scraping Google Maps
│   ├── scraper_tool.py       # WebScraperTool (httpx+BS4 / Playwright fallback)
│   ├── dedup_tool.py         # deduplicate_leads() — SIN dependencia de crewai
│   └── excel_tool.py         # export_to_excel() — SIN dependencia de crewai
│
├── prompts/
│   ├── __init__.py
│   ├── enrichment_prompt.py  # EnrichmentLLMOutput + build_enrichment_prompt()
│   ├── profiler_prompt.py    # ProfilerLLMOutput + PROFILER_SYSTEM_PROMPT
│   ├── visit_timing_prompt.py# TimingLLMOutput + build_timing_prompt()
│   └── qualifier_prompt.py   # QualifierLLMOutput + QUALIFIER_SYSTEM_PROMPT
│
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── smoke_config.yaml # Config mínima: sources=[duckduckgo], max_leads=5
│   ├── test_models.py        # 21 tests — Pydantic models, Hormozi formula
│   ├── test_config.py        # 6 tests — YAML loading, API key validation
│   ├── test_dedup.py         # 15 tests — dedup logic
│   └── test_scraper.py       # 13 tests — extraction helpers
│
└── output/                   # .gitkeep — aquí se generan los xlsx y run_logs
```

---

## 4. Modelos de datos (`models.py`) — cadena de transformación

```
RawLead
  └─► EnrichedLead         (+ lead_summary, digital_maturity, sales_opportunity)
        └─► ProfiledLead   (+ CommercialProfile, VisitTiming)
              └─► QualifiedLead (+ final_score, tier, contact_priority, pitch_hook)
```

### Modelos LLM (`with_structured_output`)
| Modelo | Agente | Campos |
|--------|--------|--------|
| `EnrichmentLLMOutput` | EnrichmentAgent | lead_summary, estimated_size, main_sector, digital_maturity, sales_opportunity |
| `ProfilerLLMOutput` | ProfilerAgent | 4 dims Hormozi + buyer_type + 3 Cardone + pitch_hook |
| `TimingLLMOutput` | VisitTimingAgent | best_visit_windows, best_call_time, worst_times, timing_confidence, timing_summary |
| `QualifierLLMOutput` | QualifierAgent | final_score, tier, discard_reason, contact_priority |

### `CommercialProfile` — `@model_validator(mode="after")` SIEMPRE sobreescribe `hormozi_score`
```python
hormozi_score = (urgency + buying_power + accessibility + market_fit) * (10 / 12)
```

### `VisitTiming` — usa `List[Dict[str, Any]]` planos (NO sub-modelos Pydantic)
```python
best_visit_windows: List[Dict[str, Any]]
best_call_time: Dict[str, Any]
worst_times: List[Dict[str, Any]]
timing_confidence: Literal["high", "inferred"]
timing_summary: str
```

---

## 5. Decisiones de arquitectura importantes

### 5.1 Flujo programático (NO `Process.hierarchical`)
`crew.py` orquesta los agentes manualmente con Python puro + `ThreadPoolExecutor`. **No usa** `crewai.Crew` con `Process.hierarchical` por inestabilidad con 8+ agentes y para mejor control de tokens.

```python
# Pasos 1+2 en paralelo
with ThreadPoolExecutor(max_workers=2) as ex:
    f_search = ex.submit(SearchAgent.run, ...)
    f_maps   = ex.submit(MapsAgent.run, ...)

# Pasos timing+profiler en paralelo
with ThreadPoolExecutor(max_workers=2) as ex:
    f_timing  = ex.submit(VisitTimingAgent.run, ...)
    f_profiler = ex.submit(ProfilerAgent.run, ...)
```

### 5.2 `tools/__init__.py` está VACÍO
`crewai.tools.BaseTool` no debe importarse a nivel de módulo en `__init__.py` — rompe los tests unitarios (que no tienen `crewai` instalado en CI). Cada tool importa solo lo que necesita dentro de su propio archivo.

### 5.3 Import condicional de `BaseTool` en `scraper_tool.py`
```python
try:
    from crewai.tools import BaseTool as _BaseTool
except ImportError:
    class _BaseTool:  # stub mínimo para tests
        name: str = ""
        description: str = ""
        def _run(self, *args, **kwargs) -> str: return ""
```
**Esto es intencional.** `dedup_tool.py` y `excel_tool.py` **no tienen** dependencia de crewai en absoluto.

### 5.4 `ChatBedrock` — parámetros correctos (langchain-aws >= 0.2)
```python
# CORRECTO:
ChatBedrock(
    client=client,
    model=settings.bedrock_model_id,          # ← "model", NO "model_id"
    model_kwargs={"temperature": temperature, "max_tokens": 4096},
)
```
`model_id` fue el nombre en versiones antiguas — **NO usar**.

### 5.5 Deduplicación — orden de prioridad en merge
```
google_maps > tavily > brave > duckduckgo
```
Lógica en `tools/dedup_tool.py::deduplicate_leads()`.

---

## 6. `config.py` — detalles que importan

- Mensajes de error en **español**: `"Archivo de configuración no encontrado: {path}"`
- `load_config(path, overrides=None)` — `overrides` es un `dict` Python, NO vars de entorno
- `AppSettings` carga de `.env` via `pydantic-settings`; en WSL el `.env` va en la raíz del proyecto

---

## 7. Formulario de score (`qualifier_agent.py`)

```python
score = (
    (hormozi_score / 10) * 0.35
  + challenger_score      * 0.20   # 0.0–1.0 según buyer_type
  + (digital_score / 10)  * 0.15   # inverso de madurez digital
  + (rating / 5)          * 0.10
  + cardone_score         * 0.20   # 0.0–1.0 según commitment_level
) * 10
```

Tiers por defecto (configurables en YAML):
- `final_score >= 7.0` → **HOT**
- `final_score >= 4.5` → **WARM**
- `final_score < 4.5`  → **COLD**

---

## 8. Variables de entorno (`.env`)

```dotenv
# LLM — Bedrock (necesitas AWS configurado)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# LLM — OpenAI (alternativa o fallback)
OPENAI_API_KEY=

# Search
TAVILY_API_KEY=
BRAVE_API_KEY=

# Maps
GOOGLE_MAPS_API_KEY=

# Overrides opcionales
LLM_PROVIDER=openai   # bedrock | openai
LLM_TEMPERATURE=0.2
```

---

## 9. Setup en WSL (Ubuntu 22.04)

```bash
cd ~/repositories/client_prospective_agents

# Crear venv con Python 3.10
python3.10 -m venv .venv
source .venv/bin/activate

# Instalar dependencias core (tests pasan sin crewai)
pip install pydantic>=2.0 pydantic-settings>=2.0 pyyaml>=6.0 \
    rapidfuzz>=3.0 unidecode httpx beautifulsoup4 pytest

# Instalar dependencias de producción completas
pip install crewai>=0.80 langchain-aws>=0.2 langchain-openai>=0.2 \
    langchain-core>=0.2 boto3 tavily-python>=0.5 \
    duckduckgo-search>=6.0 playwright>=1.44 openpyxl>=3.1 rich>=13.0

# Playwright: instalar navegador Chromium
playwright install chromium

# Copiar y editar variables de entorno
cp .env.example .env
nano .env   # añadir al menos OPENAI_API_KEY

# Verificar tests
python -m pytest tests/ -q

# Smoke test (sin API keys externas salvo OpenAI)
python main.py --config tests/fixtures/smoke_config.yaml --max-leads 5 --llm openai
```

---

## 10. Tests — estado actual

```
tests/test_models.py     21 tests ✅
tests/test_config.py      6 tests ✅
tests/test_dedup.py      15 tests ✅
tests/test_scraper.py    13 tests ✅
─────────────────────────────────
TOTAL                    55/55   ✅  (0.98s sin crewai instalado)
```

**Tests pendientes** (requieren crewai + deps producción):
- `tests/test_excel_tool.py` — validar Excel con openpyxl
- `tests/test_*_agent.py` — integración con LLM mockeado

---

## 11. Pendientes del roadmap

| Ticket | Descripción | Prioridad |
|--------|-------------|-----------|
| T026 | `tests/test_excel_tool.py` — Excel E2E con 20 leads | P0 |
| T027 | `output_agent.py` — generar `run_log_{timestamp}.json` | P2 |
| T029 | Tests de integración de agentes (LLM mockeado) | P1 |
| T030 | Smoke test end-to-end | P1 |
| T031 | README para el equipo de ventas | P2 |

---

## 12. Errores conocidos / pitfalls importantes

| Archivo | Error / Pitfall | Resolución |
|---------|-----------------|------------|
| `llm_factory.py` | `ChatBedrock` usaba `model_id=` (roto en langchain-aws ≥ 0.2) | ✅ Corregido: usar `model=` |
| `tools/__init__.py` | Imports de crewai rompían tests unitarios | ✅ Corregido: archivo vacío |
| `scraper_tool.py` | `from pydantic import BaseModel as _BaseTool` — pyright error | ✅ Corregido: stub class propio |
| `models.py` | `VisitTiming` usaba sub-modelos Pydantic pero `TimingLLMOutput` retornaba dicts | ✅ Corregido: todo `List[Dict]` |
| `models.py` | `QualifierLLMOutput` tenía campo `pitch_hook` duplicado | ✅ Corregido: removido |
| `config.py` | Error message en español, no inglés | Intencional — tests lo esperan en español |
| `test_dedup.py` | Lógica de "misma área" mal entendida | ✅ Corregido: separado en 2 tests |

---

## 13. Contexto de negocio (para prompts LLM)

- **Cliente**: Growth Guard — empresa colombiana de consultoría de ventas "Challenger Sale"
- **Producto**: Curso de ventas para equipos comerciales de PYMES
- **Segmento objetivo**: Dueños/gerentes de PYMES de servicios (talleres, clínicas, restaurantes, etc.) en Bogotá
- **Libros de referencia** (en el repo raíz):
  - `El vendedor desafiante.md` — The Challenger Sale (Dixon & Adamson)
  - `Vendes o vendes.md` — Grant Cardone
  - `Og Mandino - El vendedor mas grande del mundo.md` — Og Mandino
- **Perfil STARVING_CROWD** (Hormozi): negocio con urgencia alta, poder adquisitivo, accesible y en mercado activo

---

## 14. `search_config.yaml` — estructura

```yaml
campaign:
  name: "Talleres Mecánicos Bogotá"
  city: "Bogotá, Colombia"
  language: "es"
  max_leads: 50
  target_hot_warm: 15

queries:
  - "taller mecánico Bogotá"
  - "taller de carros Bogotá"

sources:
  - google_maps
  - tavily
  - brave

scrape_websites: true
scrape_concurrency: 5

qualification:
  min_score_hot: 7.0
  min_score_warm: 4.5

output:
  filename_prefix: "prospectos_talleres_bogota"
  output_dir: "output"

llm:
  provider: "bedrock"        # bedrock | openai
  temperature: 0.2
```

---

## 15. Excel output — 5 hojas

| Hoja | Contenido | Color header |
|------|-----------|-------------|
| `HOT` | Leads tier HOT | `#C6EFCE` (verde) |
| `WARM` | Leads tier WARM | `#FFEB9C` (amarillo) |
| `COLD` | Leads tier COLD | `#D9D9D9` (gris) |
| `TODOS` | Todos los leads ordenados por `contact_priority` | — |
| `RESUMEN` | Totales, fuentes, timestamp, duración del run | — |

Columnas: 7 grupos — CONTACTO · DATOS OPERATIVOS · PERFIL HORMOZI · PERFIL CHALLENGER · PERFIL CARDONE · TIMING DE CONTACTO · PITCH

---

*Generado automáticamente por GitHub Copilot (Claude Sonnet 4.6) — 2026-03-21*

---

## MemPalace Memory Protocol

This project uses MemPalace for persistent AI memory across sessions. The MCP server is configured globally — all agents have access to 19 memory tools automatically.

### When to Save Memories
- **After completing a significant task**: Save what was done, decisions made, and why
- **After debugging sessions**: Save the root cause, fix, and patterns observed
- **When making architectural decisions**: Save the decision, alternatives considered, and rationale
- **Before ending a long session**: Save key context that the next session will need

### How to Save
Use `mempalace_add_drawer` with:
- `wing`: "client_prospective_agents" (this project's wing)
- `room`: Appropriate topic slug (e.g., "auth-migration", "deploy-config", "bug-fixes")
- `content`: Verbatim content — exact words, decisions, code snippets. Never summarize.

### How to Recall
- **Before starting work**: Call `mempalace_search` with the topic you're working on
- **When unsure about past decisions**: Search for the decision topic
- **When context seems missing**: Check `mempalace_kg_query` for entity relationships

### Agent Diary
Each agent can maintain a personal diary via `mempalace_diary_write` / `mempalace_diary_read`. Use this for session-level notes, observations, and learnings.

### Available Tools (19 total)
- Palace read: `mempalace_status`, `mempalace_search`, `mempalace_list_wings`, `mempalace_list_rooms`, `mempalace_get_taxonomy`, `mempalace_check_duplicate`, `mempalace_get_aaak_spec`
- Palace write: `mempalace_add_drawer`, `mempalace_delete_drawer`
- Knowledge Graph: `mempalace_kg_query`, `mempalace_kg_add`, `mempalace_kg_invalidate`, `mempalace_kg_timeline`, `mempalace_kg_stats`
- Navigation: `mempalace_traverse`, `mempalace_find_tunnels`, `mempalace_graph_stats`
- Diary: `mempalace_diary_write`, `mempalace_diary_read`

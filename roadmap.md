# 🗺️ Roadmap — Sistema Multi-Agente de Prospección de Leads
**Proyecto**: Growth Guard · Lead Prospecting Agents  
**Framework**: CrewAI · Bedrock/OpenAI · Google Maps · Tavily/Brave · Excel Output  
**PM Owner**: TBD  
**Fecha base**: 2026-03-21  
**Última actualización**: 2026-03-21  
**Estimación total**: ~13 días de desarrollo (1 desarrollador senior full-time)  
**Estado actual**: 🟢 EP-0 → EP-4 + EP-6 COMPLETADOS · Pendiente: EP-5 (Excel E2E), README, E2E real con APIs

---

## Índice de Epics

| Epic | Nombre | Tickets | Est. días | Estado |
|------|--------|---------|-----------|--------|
| [EP-0](#ep-0--setup--fundamentos) | Setup & Fundamentos | 5 tickets | 1.5 d | ✅ DONE |
| [EP-1](#ep-1--capa-de-tools) | Capa de Tools | 7 tickets | 2.5 d | ✅ DONE |
| [EP-2](#ep-2--agentes-crewai) | Agentes CrewAI | 8 tickets | 4.0 d | ✅ DONE |
| [EP-3](#ep-3--prompts--structured-output) | Prompts & Structured Output | 3 tickets | 1.0 d | ✅ DONE |
| [EP-4](#ep-4--orquestación-crew) | Orquestación Crew | 2 tickets | 1.5 d | ✅ DONE |
| [EP-5](#ep-5--output--excel) | Output & Excel | 2 tickets | 1.0 d | 🔶 PENDIENTE |
| [EP-6](#ep-6--testing--qa) | Testing & QA | 5 tickets | 2.0 d | 🔶 PARCIAL |
| **Total** | | **32 tickets** | **~13.5 días** | |

---

## Convenciones de Tickets

```
[TICKET-ID] Título
Tipo:         feature | bugfix | chore | spike
Prioridad:    P0 (bloqueante) | P1 (crítico) | P2 (importante) | P3 (nice-to-have)
Estimación:   horas de desarrollo
Dependencias: ticket(s) que deben estar Done primero
Descripción:  contexto y motivación
Criterios de aceptación: lista verificable (checklist)
Notas técnicas: detalles de implementación relevantes
```

---

## EP-0 · Setup & Fundamentos ✅ DONE

> Objetivo: tener el esqueleto del proyecto corriendo, con modelos tipados y config cargable antes de tocar ningún agente.

---

### TICKET-001 · Estructura de directorios y setup del proyecto ✅

```
Tipo:       chore
Prioridad:  P0
Est.:       2 h
Deps.:      ninguna
Estado:     DONE
```

**Descripción**  
Crear la estructura de archivos definida en `requirements.md §11` y el entorno virtual con todas las dependencias pinneadas.

**Criterios de aceptación**
- [x] Carpetas creadas: `agents/`, `tools/`, `prompts/`, `output/`
- [x] `requirements.txt` con versiones exactas de todas las librerías del stack (§10)
- [x] `.env.example` con todas las variables de §12 documentadas
- [x] `.gitignore` que excluye `.env`, `output/`, `__pycache__/`, `.venv/`
- [ ] `python -m venv .venv && pip install -r requirements.txt` ejecuta sin errores *(pendiente instalar deps producción)*
- [ ] `playwright install chromium` ejecuta sin errores *(pendiente)*

**Notas técnicas**
```
crewai>=0.80
langchain-aws>=0.2
langchain-openai>=0.2
tavily-python>=0.5
duckduckgo-search>=6.0
httpx>=0.27
beautifulsoup4>=4.12
playwright>=1.44
rapidfuzz>=3.0
openpyxl>=3.1
pydantic-settings>=2.0
pyyaml>=6.0
rich>=13.0
```

---

### TICKET-002 · Modelos de datos (Pydantic) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       3 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar todos los modelos de datos en `models.py` usando Pydantic v2. Cada modelo hereda del anterior siguiendo la cadena de transformación del pipeline.

**Criterios de aceptación**
- [x] `SearchConfig` — valida que `queries` sea `List[str]` no vacío, `max_leads > 0`
- [x] `RawLead` — todos los campos de §6, `popular_times` acepta lista vacía por defecto
- [x] `EnrichedLead(RawLead)` — herencia correcta, campos con defaults razonables
- [x] `CommercialProfile` — scores con validación de rango (`0 <= hormozi_urgency <= 3`)
- [x] `VisitTiming` — `timing_confidence` acepta solo `"high"` o `"inferred"` (Literal); campos internos usan `List[Dict]`
- [x] `ProfiledLead(EnrichedLead)` — contiene `profile: CommercialProfile` y `visit_timing: VisitTiming`
- [x] `QualifiedLead(ProfiledLead)` — `tier` acepta solo `"HOT"/"WARM"/"COLD"` (Literal)
- [x] `RunReport` — campos: `campaign_name`, `total_raw`, `total_after_dedup`, `hot_count`, `warm_count`, `cold_count`, `sources_breakdown: dict`, `duration_seconds: float`, `iterations: int`
- [x] `pytest tests/test_models.py` — 21 tests pasando

**Notas técnicas**
- Usar `model_validator` de Pydantic v2 para validar `hormozi_score = sum([urgency, buying_power, accessibility, market_fit]) * (10/12)`
- `popular_times: List[dict] = Field(default_factory=list)`
- `social_links: dict = Field(default_factory=dict)`

---

### TICKET-003 · Config loader (SearchConfig + .env) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `config.py`: carga `search_config.yaml`, valida con Pydantic, expone variables de entorno via `pydantic-settings`. El sistema nunca debe hardcodear queries ni API keys.

**Criterios de aceptación**
- [x] `load_config(path: str) -> SearchConfig` lee y valida el YAML
- [x] `AppSettings` (pydantic-settings) carga todas las vars de `.env` (§12)
- [x] Si falta una API key requerida por los `sources` configurados → lanza `ConfigError` con mensaje claro
- [x] Si `sources` incluye `duckduckgo` → no exige API key (modo local)
- [x] `load_config` acepta override de campos via dict de overrides
- [x] `search_config.yaml` funcional para campaña "Talleres Bogotá"
- [x] `pytest tests/test_config.py` — 6 tests pasando

---

### TICKET-004 · LLM provider factory (Bedrock + OpenAI fallback) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-003
Estado:     DONE
```

**Descripción**  
Crear `llm_factory.py` que instancia el LLM correcto según `llm.provider` y tiene retry automático con fallback a OpenAI si Bedrock falla.

**Criterios de aceptación**
- [x] `get_llm(settings: AppSettings) -> BaseChatModel` retorna Bedrock o OpenAI
- [x] Si Bedrock lanza `ClientError` (throttling/timeout) → reintenta 2x con backoff exponencial, luego hace fallback a OpenAI
- [x] Log con `rich` indica qué LLM se está usando en cada momento
- [x] `get_llm` acepta `temperature` como parámetro (default desde config)
- [x] Bug fix aplicado: `ChatBedrock` usa `model=` (no `model_id=`) per langchain-aws ≥ 0.2

**Notas técnicas**
```python
# Bedrock
from langchain_aws import ChatBedrock
# OpenAI
from langchain_openai import ChatOpenAI
```

---

### TICKET-005 · CLI entry point (main.py) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       1.5 h
Deps.:      TICKET-003, TICKET-004
Estado:     DONE
```

**Descripción**  
Crear `main.py` como entry point con argumentos CLI usando `argparse`.

**Criterios de aceptación**
- [x] `python main.py --config search_config.yaml` arranca el sistema
- [x] `--config` requerido; si no se provee → error claro
- [x] `--dry-run` flag: valida config y APIs sin ejecutar el crew
- [x] `--max-leads N` override del valor en YAML
- [x] `--llm bedrock|openai` override del provider
- [x] `--no-scrape` flag para deshabilitar scraping de sitios web
- [x] Banner de inicio con `rich` que muestra: campaign name, queries, city, max_leads, sources activos, LLM provider
- [x] Al finalizar: muestra `RunReport` con tabla `rich` (totales por tier, fuentes, duración)

---

## EP-1 · Capa de Tools ✅ DONE

> Objetivo: todas las herramientas de integración con APIs y scraping, independientes de los agentes, testeables de forma aislada.

---

### TICKET-006 · TavilySearchTool ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/tavily_tool.py` como `BaseTool` de CrewAI que busca resultados web con Tavily API.

**Criterios de aceptación**
- [x] `TavilySearchTool(query: str, max_results: int = 10) -> str (JSON)`
- [x] Retorna: `[{url, title, snippet, domain, score}]`
- [x] Filtra resultados con `score < 0.5` (baja relevancia)
- [x] Timeout de 10s por request; en timeout → retorna lista vacía con log warning
- [x] Rate limiting: máximo 5 req/seg (sleep entre calls)

**Notas técnicas**
```python
from tavily import TavilyClient
client = TavilyClient(api_key=settings.TAVILY_API_KEY)
response = client.search(query, max_results=max_results, search_depth="advanced")
```

---

### TICKET-007 · BraveSearchTool ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/brave_tool.py` que hace requests REST a `https://api.search.brave.com/res/v1/web/search`.

**Criterios de aceptación**
- [x] `BraveSearchTool(query: str, country: str = "co", max_results: int = 20) -> str (JSON)`
- [x] Headers: `Accept: application/json`, `X-Subscription-Token: {BRAVE_API_KEY}`
- [x] Paginación: soporta `offset` para obtener hasta 100 resultados
- [x] Retorna: `[{url, title, description, domain}]`
- [x] Maneja HTTP 429 (rate limit): exponential backoff 1s, 2s, 4s

---

### TICKET-008 · DuckDuckGoTool (modo local/dev) ✅

```
Tipo:       feature
Prioridad:  P2
Est.:       1 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/duckduckgo_tool.py` para uso en desarrollo sin API key.

**Criterios de aceptación**
- [x] `DuckDuckGoSearchTool(query: str, max_results: int = 20) -> str (JSON)`
- [x] Usa `duckduckgo_search.DDGS().text()`, `region=co-es`
- [x] Maneja `DuckDuckGoSearchException` → retorna lista vacía con log warning
- [x] Mismo formato de output que Tavily/Brave: `[{url, title, snippet, domain}]`
- [x] Habilitado automáticamente si `duckduckgo` está en `sources` del config

---

### TICKET-009 · GooglePlacesTool + GooglePlaceDetailsTool ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       3 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/maps_tool.py` con dos herramientas: búsqueda por texto y detalle de un lugar específico.

**Criterios de aceptación**

**GoogleMapsSearchTool:**
- [x] Endpoint: `POST https://places.googleapis.com/v1/places:searchText`
- [x] Fields mask completo via `X-Goog-FieldMask` header
- [x] Paginación via `pageToken` (hasta 3 páginas, sleep 2s entre páginas)
- [x] Filtra `businessStatus != "OPERATIONAL"`

**GoogleMapsDetailsTool:**
- [x] `get_place_details(place_id: str) -> dict`
- [x] Fields mask adiciona `regularOpeningHours,currentOpeningHours`
- [x] Retorna `RawLead`-compatible dict completo
- [x] `popular_times = []` cuando la API no los entrega (rellenado por PopularTimesTool)

**Notas técnicas**
```
API Key header: X-Goog-Api-Key: {GOOGLE_MAPS_API_KEY}
Field mask header: X-Goog-FieldMask: places.id,places.displayName,...
```

---

### TICKET-010 · PopularTimesTool (scraping HTML fallback) ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/popular_times_tool.py` para extraer datos de "Popular times" directamente del HTML de Google Maps via Playwright cuando la API no los entrega.

**Criterios de aceptación**
- [x] `PopularTimesTool._run(place_id: str) -> str (JSON)`
- [x] URL: `https://www.google.com/maps/place/?q=place_id:{place_id}`
- [x] Playwright en modo headless, User-Agent rotativo (3 opciones)
- [x] Extrae info del script JS `window.APP_INITIALIZATION_STATE`
- [x] Output: `{popular_times: [...], confidence: "high"|"inferred"}`
- [x] Si "Popular times" no existe → retorna `[]` sin error
- [x] Timeout de página 15s; si supera → retorna `[]` con log warning
- [x] Rate limit: sleep 3s entre scrapes para evitar bloqueo

**Notas técnicas**
- Google Maps renderiza las barras de popular times como elementos con `aria-label="X% de ocupación"` o en el JSON de inicialización de la app. Priorizar el JSON pues es más estable.
- Verificar con `place_id` de un taller real como smoke test manual.

---

### TICKET-011 · StaticScraperTool + PlaywrightScraperTool ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-001
Estado:     DONE
```

**Descripción**  
Implementar `tools/scraper_tool.py` con dos estrategias de scraping y heurística de selección automática.

**Criterios de aceptación**

**Heurística de selección:**
- [x] `_JS_SIGNALS` set: detecta SPAs via markers en HTML (`__NEXT_DATA__`, `ng-version`, `wix.com/static`, etc.)

**ScraperTool (unificado):**
- [x] httpx GET estático → Playwright fallback si se detectan JS signals
- [x] BS4: extrae `og:description`, `schema.org LocalBusiness`, meta description
- [x] Regex emails colombianos, teléfonos, WhatsApp links
- [x] Detecta redes sociales: instagram, facebook, tiktok, linkedin
- [x] Detecta tech stack: WordPress, Shopify, Wix, custom
- [x] `pytest tests/test_scraper.py` — 13 tests pasando

**Nota**: `BaseTool` import condicional (try/except) para permitir tests sin `crewai` instalado.

---

### TICKET-012 · ExcelExportTool ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `tools/excel_tool.py` que genera el Excel final con todas las hojas, columnas y formato visual.

**Criterios de aceptación**
- [x] Genera archivo `output/leads_{campaign}_{YYYYMMDD}.xlsx`
- [x] Hojas: `HOT`, `WARM`, `COLD`, `TODOS`, `RESUMEN`
- [x] Columnas en 7 grupos: CONTACTO, DATOS OPERATIVOS, PERFIL HORMOZI, PERFIL CHALLENGER, PERFIL CARDONE, TIMING DE CONTACTO, PITCH
- [x] Colores por fila: HOT `#C6EFCE`, WARM `#FFEB9C`, COLD `#D9D9D9`
- [x] Header: `PatternFill` fondo `#243F60`, texto blanco, negrita
- [x] `pitch_hook`: wrap text, column width 60
- [x] `timing_summary`: fill `#DEEAF1`, wrap text, width 50
- [x] Filas con `timing_confidence == "inferred"`: font italic, color gris `#808080`
- [x] Hoja `RESUMEN`: totales por tier, fuentes, timestamp run, duración
- [x] Auto-filter en header de cada hoja, freeze panes fila 1

---

## EP-2 · Agentes CrewAI ✅ DONE

> Objetivo: implementar los 8 agentes con sus roles, goals, backstories y tools correctamente conectados. Cada agente es una clase con método `create() -> Agent`.

---

### TICKET-013 · SearchAgent (Tavily + Brave + DDG) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       3 h
Deps.:      TICKET-006, TICKET-007, TICKET-008, TICKET-003
Estado:     DONE
```

**Descripción**  
Implementar `agents/search_agent.py` con lógica de expansión de queries + búsqueda multi-fuente.

**Criterios de aceptación**
- [x] `SearchAgent.run(config, settings, llm) -> List[RawLead]`
- [x] LLM expande base queries en 3-5 variaciones
- [x] Tools instanciados según `sources` en config
- [x] Retorna `List[RawLead]` con `source` seteado por herramienta

---

### TICKET-014 · MapsAgent (Google Places) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-009, TICKET-003
Estado:     DONE
```

**Descripción**  
Implementar `agents/maps_agent.py`.

**Criterios de aceptación**
- [x] `MapsAgent.run(config, settings) -> List[RawLead]`
- [x] `GoogleMapsSearchTool` + `GoogleMapsDetailsTool` por cada lugar
- [x] Maneja paginación (`pageToken`) hasta `max_leads`
- [x] Output: `List[RawLead]` con `source="google_maps"`

---

### TICKET-015 · ScraperAgent ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-011, TICKET-003
Estado:     DONE
```

**Descripción**  
Implementar `agents/scraper_agent.py`.

**Criterios de aceptación**
- [x] `ScraperAgent.run(leads, config, concurrency) -> List[RawLead]`
- [x] `ThreadPoolExecutor` para scraping concurrente
- [x] Scraping omitido si `scrape_websites = false` en config
- [x] Datos scrapeados almacenados como JSON blob en `raw_snippet` del lead

---

### TICKET-016 · EnrichmentAgent

```
Tipo:       feature
Prioridad:  P0
Est.:       3 h
Deps.:      TICKET-002, TICKET-003, TICKET-004
```

**Descripción**  
Implementar `agents/enrichment_agent.py` con lógica de deduplicación fuzzy y enriquecimiento LLM.

**Criterios de aceptación**
- [ ] `EnrichmentAgent.create(settings: AppSettings) -> Agent`
- [ ] `role`, `goal`, `backstory` exactos según §3.4
- [ ] `tools = [DeduplicationTool]`
- [ ] `EnrichmentTask.create(raw_leads: List[RawLead]) -> Task`
- [ ] Task incluye: instrucción de deduplicación con clave `(nombre_normalizado, primeros_7_digitos_telefono)`
- [ ] Task incluye: en merge, prioridad Maps > Brave > Scraper
- [ ] Task llama LLM para generar `lead_summary`, `estimated_size`, `main_sector`, `digital_maturity`, `sales_opportunity` por cada lead dedup
- [ ] Output: `List[EnrichedLead]` JSON
- [ ] Log: `"{N_raw} leads crudos → {N_dedup} leads únicos ({N_merged} mergeados)"`

---

### TICKET-017 · VisitTimingAgent ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-010, TICKET-003, TICKET-004
Estado:     DONE
```

**Descripción**  
Implementar `agents/visit_timing_agent.py`.

**Criterios de aceptación**
- [x] `VisitTimingAgent.run(enriched_leads, llm) -> Dict[str, VisitTiming]`
- [x] Prefetch: `PopularTimesTool` para todos los leads con `place_id` y `popular_times` vacío
- [x] LLM via `with_structured_output(TimingLLMOutput)` por lead
- [x] `timing_confidence = "inferred"` cuando `popular_times` original era vacío
- [x] Retorna dict keyed by `place_id or name` para merge downstream

---

### TICKET-018 · ProfilerAgent (Hormozi + Challenger + Cardone) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       4 h
Deps.:      TICKET-002, TICKET-004, TICKET-021
Estado:     DONE
```

**Descripción**  
Implementar `agents/profiler_agent.py`.

**Criterios de aceptación**
- [x] `ProfilerAgent.run(enriched_leads, llm) -> List[ProfiledLead]`
- [x] LLM aplica los 3 frameworks por lead via `with_structured_output(ProfilerLLMOutput)`
- [x] `CommercialProfile` con `@model_validator` que auto-computa `hormozi_score`
- [x] Scores Hormozi validados en rango 0-3 por dimensión
- [x] Output: `List[ProfiledLead]`

---

### TICKET-019 · QualifierAgent ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-002, TICKET-004, TICKET-022
Estado:     DONE
```

**Descripción**  
Implementar `agents/qualifier_agent.py` con la fórmula de score determinística + validación LLM.

**Criterios de aceptación**
- [x] `QualifierAgent.run(profiled_leads, config, llm) -> List[QualifiedLead]`
- [x] Score determinístico: `hormozi*0.35 + challenger*0.20 + digital*0.15 + rating*0.10 + cardone*0.20`
- [x] LLM valida/refina con `with_structured_output(QualifierLLMOutput)`
- [x] Tiers según umbrales de config (`min_score_hot`, `min_score_warm`)
- [x] `contact_priority`: 1-N ordenado por score DESC
- [x] `discard_reason` solo si `tier = "COLD"`
- [x] Output: `List[QualifiedLead]` ordenado por `contact_priority`

---

### TICKET-020 · OutputAgent ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       1.5 h
Deps.:      TICKET-012, TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `agents/output_agent.py`.

**Criterios de aceptación**
- [x] `OutputAgent.run(qualified_leads, report, config) -> str (excel path)`
- [x] Llama `export_to_excel()` y genera el archivo
- [x] Imprime tabla Rich con Top 5 HOT leads y estadísticas del run

---

## EP-3 · Prompts & Structured Output ✅ DONE

> Objetivo: prompts centralizados, versionables y probados de forma aislada. Todo output LLM usa `with_structured_output`.

---

### TICKET-021 · Prompts del ProfilerAgent ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       3 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `prompts/profiler_prompt.py`.

**Criterios de aceptación**
- [x] `PROFILER_SYSTEM_PROMPT`: 3 frameworks con ejemplos de aplicación + contexto Growth Guard
- [x] `build_profiler_prompt(lead: EnrichedLead) -> str`
- [x] Sección Hormozi: 4 criterios con ejemplos de score 0/1/2/3
- [x] Sección Challenger: 5 perfiles de comprador del SEC
- [x] Sección Cardone: commitment, objeciones típicas de PYMES Colombia

---

### TICKET-022 · Prompts del QualifierAgent y EnrichmentAgent ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `prompts/qualifier_prompt.py` y `prompts/enrichment_prompt.py`.

**Criterios de aceptación**

**enrichment_prompt.py:** ✅
- [x] `EnrichmentLLMOutput` (Pydantic): `lead_summary, estimated_size, main_sector, digital_maturity, sales_opportunity`
- [x] Prompt contextualiza PYMES de servicios Colombia
- [x] Escala `estimated_size`: micro/pequeño/mediano/grande

**qualifier_prompt.py:** ✅
- [x] `QualifierLLMOutput` (Pydantic): `final_score, tier, discard_reason, contact_priority`
- [x] `pitch_hook` generado en `profiler_prompt.py` (parte del perfil completo)

---

### TICKET-023 · Prompts del VisitTimingAgent ✅

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `prompts/visit_timing_prompt.py`.

**Criterios de aceptación**
- [x] `TimingLLMOutput` (Pydantic): schema completo de `VisitTiming` para `with_structured_output`
- [x] `build_timing_prompt(lead: EnrichedLead) -> str`
- [x] Prompt incluye el algoritmo completo de §3.5 como instrucciones
- [x] Modo "inferred" cuando `popular_times` vacío con instrucciones por tipo de negocio

---

## EP-4 · Orquestación Crew ✅ DONE

> Objetivo: ensamblar todos los agentes en flujo orquestado con re-iteración y RunReport.

---

### TICKET-024 · Crew assembly y flujo principal ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       4 h
Deps.:      TICKET-013 al TICKET-020, TICKET-004
Estado:     DONE
```

**Descripción**  
Implementar `crew.py` con `ProspectingCrew` y flujo programático (hybrid — no `Process.hierarchical` para mayor control y eficiencia de tokens).

**Criterios de aceptación**
- [x] `ProspectingCrew(config: SearchConfig, settings: AppSettings)`
- [x] Pasos 1+2 (Search + Maps) en `ThreadPoolExecutor(max_workers=2)` paralelo
- [x] Pasos 5+6 (VisitTiming + Profiler) también paralelos
- [x] `crew.kickoff()` retorna `RunReport`
- [x] Log `rich` en cada paso con conteo de leads y timing

**Lógica de re-iteración:**
- [x] Si `HOT + WARM < config.target_hot_warm` Y `iterations < 3`
- [x] LLM genera 3 nuevas queries, re-ejecuta discovery + enrichment
- [x] `_MAX_ITERATIONS = 3`

---

### TICKET-025 · DeduplicationTool (rapidfuzz) ✅

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-002
Estado:     DONE
```

**Descripción**  
Implementar `tools/dedup_tool.py` con lógica de deduplicación fuzzy.

**Criterios de aceptación**
- [x] `deduplicate_leads(leads, threshold=85) -> List[RawLead]`
- [x] Normalización: lowercase, `unidecode`, quitar sufijos legales
- [x] Clave secundaria: primeros 7 dígitos del teléfono
- [x] `rapidfuzz.fuzz.token_sort_ratio > 85` + misma `city` → merge
- [x] Prioridad en merge: google_maps > tavily > brave > duckduckgo
- [x] `pytest tests/test_dedup.py` — 15 tests pasando

---

## EP-5 · Output & Excel 🔶 PENDIENTE

> Los tests de esta epic confirman el artefacto final que verá el equipo de ventas.

---

### TICKET-026 · Integración end-to-end del Excel 🔶 PENDIENTE

```
Tipo:       feature
Prioridad:  P0
Est.:       2 h
Deps.:      TICKET-012, TICKET-019, TICKET-020
Estado:     PENDIENTE
```

**Descripción**  
Validar que el Excel generado es correcto, completo y abre sin errores en Microsoft Excel y LibreOffice.

**Criterios de aceptación**
- [ ] Generar Excel con dataset de prueba de 20 leads (5 HOT, 10 WARM, 5 COLD)
- [ ] Verificar que las 5 hojas existen y tienen datos correctos
- [ ] Verificar colores de fila por tier con openpyxl
- [ ] Verificar que `contact_priority` es continuo (1, 2, 3... sin gaps) en hoja TODOS
- [ ] Verificar que hoja RESUMEN tiene: total leads, % por tier, fuentes, timestamp
- [ ] Archivo no supera 5MB para 200 leads
- [ ] Nombre de archivo incluye fecha: `prospectos_talleres_bogota_20260321.xlsx`

---

### TICKET-027 · JSON Run Log ✅ DONE

```
Tipo:       feature
Prioridad:  P2
Est.:       1 h
Deps.:      TICKET-024
Estado:     PENDIENTE
```

**Descripción**  
Generar `run_log_{timestamp}.json` con metadata completa del run para auditoría y reproducibilidad.

**Criterios de aceptación**
- [ ] Archivo JSON válido con: `campaign_name`, `timestamp`, `duration_seconds`, `config_snapshot`, `RunReport` completo
- [ ] `config_snapshot`: copia del YAML usado (sin API keys)
- [ ] `sources_breakdown`: `{tavily: N, brave: N, google_maps: N, duckduckgo: N}`
- [ ] `iterations_used: int`
- [ ] `leads_per_iteration: List[int]`
- [ ] `error_log: List[{agent, error, timestamp}]` (errores no fatales capturados)

---

## EP-6 · Testing & QA 🔶 PARCIAL (55/55 unitarios ✅ · integración + smoke pendientes)

> Objetivo: cobertura de los caminos críticos del pipeline. No coverage exhaustiva — foco en los contratos entre agentes y las herramientas de integración externa.

---

### TICKET-028 · Tests unitarios de Tools 🔶 PARCIAL

```
Tipo:       chore
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-006 al TICKET-012, TICKET-025
Estado:     PARCIAL
```

**Descripción**  
Tests unitarios para cada herramienta con mocks de las APIs externas.

**Criterios de aceptación**
- [ ] `test_tavily_tool.py`: mock de `TavilyClient.search` *(pendiente)*
- [ ] `test_brave_tool.py`: mock httpx, paginación y 429 *(pendiente)*
- [ ] `test_maps_tool.py`: mock API Places *(pendiente)*
- [x] `test_scraper_tool.py`: 13 tests — extracción email/phone/WhatsApp/social/tech + SPA detection
- [x] `test_dedup_tool.py`: 15 tests — dedup place_id/phone/fuzzy + merge correcto
- [x] `test_models.py`: 21 tests — Pydantic models, Hormozi formula, RunReport
- [x] `test_config.py`: 6 tests — YAML loading, overrides, API key validation
- [ ] `test_excel_tool.py`: genera Excel con 3 leads *(pendiente)*
- [x] **55 tests pasan con `pytest tests/` sin acceso a internet** ✅

---

### TICKET-029 · Tests de integración de Agentes 🔶 PENDIENTE

```
Tipo:       chore
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-013 al TICKET-020
Estado:     PENDIENTE — requiere instalar deps producción primero
```

**Descripción**  
Tests de integración que verifican la cadena de transformación de datos entre agentes con LLM mockeado.

**Criterios de aceptación**
- [ ] `test_search_agent.py`: query mock → `List[RawLead]` parseable
- [ ] `test_enrichment_agent.py`: 5 RawLeads → 4 EnrichedLeads (1 dedup)
- [ ] `test_profiler_agent.py`: 3 EnrichedLeads → 3 ProfiledLeads con scores en rango
- [ ] `test_visit_timing_agent.py`: con/sin `popular_times` → `timing_confidence` correcto
- [ ] `test_qualifier_agent.py`: lead completo → HOT; lead sin contacto → COLD con `discard_reason`
- [ ] LLM mockeado — no consume tokens en CI

---

### TICKET-030 · Smoke test end-to-end (modo dev) ✅ DONE

```
Tipo:       chore
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-024, instalación deps producción
Estado:     PENDIENTE — bloqueado por instalación de crewai, langchain-aws, etc.
```

**Descripción**  
Test de humo que corre el pipeline completo en modo dev (DuckDuckGo sin API key) con `max_leads=5`.

**Pre-requisito — instalar dependencias de producción:**
```bash
pip install crewai>=0.80 langchain-aws>=0.2 langchain-openai>=0.2 \
  tavily-python>=0.5 duckduckgo-search>=6.0 playwright openpyxl \
  langchain-core boto3
playwright install chromium
```

**Criterios de aceptación**
- [X] `python main.py --config tests/fixtures/smoke_config.yaml --max-leads 5` → sin crash
- [X] `smoke_config.yaml`: `sources: [duckduckgo]`, query simple, `max_leads: 5` *(fixture ya existe)*
- [X] Archivo Excel generado en `output/`
- [X] Excel tiene al menos 1 fila en alguna hoja (HOT, WARM o COLD)
- [X] `run_log_*.json` generado
- [X] Duración total < 120 segundos

---

### TICKET-031 · README y documentación mínima 🔶 PENDIENTE

```
Tipo:       chore
Prioridad:  P2
Est.:       1.5 h
Deps.:      TICKET-030 (smoke test OK)
Estado:     PENDIENTE
```

**Descripción**  
README de uso del sistema para el equipo de Growth Guard.

**Criterios de aceptación**
- [ ] Sección: **Setup** (python version, pip install, playwright install, .env config)
- [ ] Sección: **Configurar una campaña** (editar `search_config.yaml` con ejemplo anotado)
- [ ] Sección: **Ejecutar** (`python main.py --config search_config.yaml`)
- [ ] Sección: **Entender el Excel** (descripción de cada grupo de columnas, tiers, scores)
- [ ] Sección: **Modo local sin API keys** (solo DuckDuckGo + OpenAI)
- [ ] Sección: **Quick smoke test**
- [ ] Sección: **Variables de entorno** (tabla con nombre, fuente de obtención, si es obligatoria)

---

### TICKET-032 · Prueba E2E con APIs reales (Tavily + Google Maps + OpenAI) 🔶 PENDIENTE

```
Tipo:       chore / spike
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-030 (smoke test OK), TICKET-031 (README escrito)
Estado:     PENDIENTE — depende de configuración de API keys en .env
```

**Descripción**  
Prueba end-to-end completa del pipeline usando fuentes reales: Tavily para búsqueda web y Google Places para datos de mapas. Valida que con API keys reales el sistema genere leads reales, los perfila correctamente y exporta un Excel utilizable por el equipo de ventas.

**Prerequisito — API keys requeridas en `.env`:**
```dotenv
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
GOOGLE_MAPS_API_KEY=AIza...
```

**Comando de ejecución:**
```bash
source .venv/bin/activate
python main.py --config tests/fixtures/e2e_config.yaml --max-leads 20 --llm openai
```

**Criterios de aceptación**
- [ ] Pipeline completa sin crash (exit code 0)
- [ ] Al menos 5 leads encontrados y guardados en el Excel
- [ ] Excel generado en `output/` con al menos 1 fila en hoja HOT o WARM
- [ ] `run_log_*.json` generado con `leads_summary` no vacío
- [ ] Columnas CONTACTO: nombre, teléfono o dirección presentes en ≥ 50% de los leads
- [ ] Columnas PERFIL HORMOZI: `hormozi_score` calculado (> 0) en todos los leads
- [ ] Columnas TIMING: `timing_summary` presente en todos los leads
- [ ] Duración total < 300 segundos para 20 leads
- [ ] Sin errores `LLMCallError` ni `ValidationError` no controlados en el log

**Config de prueba:** `tests/fixtures/e2e_config.yaml`  
**Output esperado:** `output/e2e_talleres_bogota_YYYYMMDD_HHmmss.xlsx`

---

## EP-7 · Auto Query Generation 🟡 NUEVO

> Objetivo: que el usuario solo describa su negocio/producto y opcionalmente pase URLs de referencia. El sistema scrapea esas URLs, entiende el contexto del negocio y genera automáticamente las queries de búsqueda de leads. Las queries manuales en `campaign.queries` pasan a ser opcionales.

---

### TICKET-033 · Modelo BusinessContext + YAML config 🔶 PENDIENTE

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-002 (Modelos), TICKET-003 (Config)
Estado:     PENDIENTE
```

**Descripción**  
Agregar al YAML de campaña una sección `business_context` con la descripción formal del negocio/producto del usuario y URLs de referencia. Crear el modelo Pydantic correspondiente y hacer que `queries` sea opcional cuando `business_context` está presente.

**Ejemplo YAML:**
```yaml
campaign:
  name: "Talleres Bogotá Q1-2026"
  city: "Bogotá"
  country: "Colombia"
  language: "es"
  max_leads: 100
  max_iterations: 5
  # queries es OPCIONAL si business_context está presente
  # queries: ["taller mecánico Bogotá"]
  business_context:
    description: >
      Growth Guard es una consultora colombiana que vende programas de capacitación
      en ventas para equipos comerciales de PYMES. Nuestro producto principal es un
      curso intensivo de 8 semanas basado en la metodología Challenger Sale, diseñado
      para dueños y gerentes comerciales de negocios de servicios (talleres, clínicas,
      restaurantes, etc.) que quieran duplicar sus ventas en 90 días.
    reference_urls:
      - "https://growthguard.co/programa-ventas"
      - "https://growthguard.co/casos-de-exito"
    target_audience: "Dueños y gerentes de PYMES de servicios en Bogotá"
    ideal_customer: "Taller mecánico, clínica odontológica, restaurante, salón de belleza con 5-50 empleados"
```

**Criterios de aceptación**
- [ ] Modelo `BusinessContext` en `models.py`: `description` (str, requerido), `reference_urls` (List[str], opcional), `target_audience` (str, opcional), `ideal_customer` (str, opcional)
- [ ] `SearchConfig.business_context` es `Optional[BusinessContext]`
- [ ] `SearchConfig.queries` acepta lista vacía si `business_context` está presente (model_validator)
- [ ] `config.py` carga la sección `business_context` del YAML
- [ ] Tests unitarios: config con solo business_context (sin queries), config con ambos, config sin ninguno falla

**Notas técnicas**
- `queries` sigue siendo obligatorio si no hay `business_context` — el validator lo verifica
- Si hay ambos (`queries` + `business_context`), el sistema usa queries como base y genera adicionales

---

### TICKET-034 · ContextAgent: scrape URLs de referencia + resumen del negocio 🔶 PENDIENTE

```
Tipo:       feature
Prioridad:  P1
Est.:       3 h
Deps.:      TICKET-033, TICKET-011 (Scraper Tool)
Estado:     PENDIENTE
```

**Descripción**  
Nuevo agente que toma el `BusinessContext` del config, scrapea las `reference_urls` usando el `WebScraperTool` existente, y genera un resumen estructurado del negocio usando el LLM. Este resumen será el input del `QueryGeneratorAgent`.

**Archivo:** `agents/context_agent.py`

**Criterios de aceptación**
- [ ] `ContextAgent.process(config, settings, llm) -> BusinessSummary`
- [ ] Scrapea cada URL en `reference_urls` concurrentemente (reutiliza `WebScraperTool`)
- [ ] Combina `description` + contenido scrapeado en un prompt al LLM
- [ ] Modelo `BusinessSummary` (Pydantic): `core_offering` (str), `target_sectors` (List[str]), `key_pain_points` (List[str]), `differentiators` (List[str]), `geographic_focus` (str), `raw_context` (str, el texto combinado, max 3000 chars)
- [ ] Usa `with_structured_output(BusinessSummary)` para parseo seguro
- [ ] Si no hay `reference_urls` o el scrape falla, genera el resumen solo con la `description`
- [ ] Timeout de 10s por URL scrapeada

---

### TICKET-035 · QueryGeneratorAgent: LLM genera queries automáticamente 🔶 PENDIENTE

```
Tipo:       feature
Prioridad:  P1
Est.:       2 h
Deps.:      TICKET-034 (ContextAgent)
Estado:     PENDIENTE
```

**Descripción**  
Nuevo agente que toma el `BusinessSummary` y genera una lista de queries de búsqueda optimizadas para encontrar leads que sean clientes potenciales del negocio descrito.

**Archivo:** `agents/query_generator_agent.py`  
**Prompt:** `prompts/query_generator_prompt.py`

**Criterios de aceptación**
- [ ] `QueryGeneratorAgent.process(summary, config, llm) -> List[str]`
- [ ] El prompt incluye: resumen del negocio, ciudad, país, idioma, target_audience, ideal_customer
- [ ] Genera 10-20 queries diversas: variaciones geográficas, sinónimos del sector, búsquedas por dolor/necesidad, búsquedas por tipo de negocio
- [ ] Si `config.queries` ya tiene valores, los combina (queries manuales primero + generadas)
- [ ] Usa `with_structured_output` con un modelo `QueryList` (List[str])
- [ ] Deduplica queries (case-insensitive, normalizado)
- [ ] Reemplaza la expansion de queries existente en `SearchAgent._expand_queries()`: si hay `business_context`, usa las queries generadas; si no, mantiene el flujo actual

---

### TICKET-036 · Integrar EP-7 en crew.py (paso 0 del pipeline) 🔶 PENDIENTE

```
Tipo:       feature
Prioridad:  P1
Est.:       1 h
Deps.:      TICKET-034, TICKET-035
Estado:     PENDIENTE
```

**Descripción**  
Integrar ContextAgent + QueryGeneratorAgent como "Paso 0" del pipeline en `crew.py`, antes del loop de iteraciones. El flujo actualizado:

```
PASO 0: (solo si business_context presente)
  → ContextAgent scrapea URLs + genera BusinessSummary
  → QueryGeneratorAgent genera queries → se inyectan en config.queries

PASO 1+2: Search + Maps (igual que antes, pero con queries enriquecidas)
... resto del pipeline sin cambios
```

**Criterios de aceptación**
- [ ] `crew.py`: si `config.business_context` existe, ejecutar paso 0 antes del loop
- [ ] Las queries generadas se loguean en consola (Rich): `"🧠 Queries auto-generadas: N"`
- [ ] Si `business_context` no existe, el pipeline funciona exactamente igual que hoy
- [ ] Las queries generadas se incluyen en el `run_log_*.json` bajo `auto_generated_queries`
- [ ] Retrocompatibilidad total: configs sin `business_context` funcionan sin cambios
- [ ] El `BusinessSummary` se incluye en el `run_log` para auditoría

---

## Dependencias Visuales

```
TICKET-001 (Setup)
    │
    ├── TICKET-002 (Modelos)
    │       └── TICKET-003 (Config)
    │               └── TICKET-004 (LLM Factory)
    │                       └── TICKET-005 (CLI main.py)
    │
    ├── TICKET-006 (Tavily) ──────────┐
    ├── TICKET-007 (Brave) ───────────┤
    ├── TICKET-008 (DDG) ─────────────┤── TICKET-013 (SearchAgent)
    ├── TICKET-009 (Maps) ────────────┼── TICKET-014 (MapsAgent)
    ├── TICKET-010 (PopularTimes) ────┼── TICKET-017 (VisitTimingAgent)
    ├── TICKET-011 (Scraper) ─────────┤── TICKET-015 (ScraperAgent)
    └── TICKET-012 (Excel) ───────────┘── TICKET-020 (OutputAgent)
                                      │
    TICKET-002 + TICKET-004 ──────────┼── TICKET-016 (EnrichmentAgent)
    TICKET-021 (Profiler Prompts) ────┼── TICKET-018 (ProfilerAgent)
    TICKET-022 (Qualifier Prompts) ───┼── TICKET-019 (QualifierAgent)
    TICKET-023 (Timing Prompts) ──────┘── TICKET-017 (VisitTimingAgent)

    TICKET-013 → 020 ─── TICKET-024 (Crew Assembly)
    TICKET-025 (Dedup) ──┘
         │
    TICKET-026 (Excel E2E)
    TICKET-027 (JSON Log)
         │
    TICKET-028 (Unit Tests Tools)
    TICKET-029 (Integration Tests)
    TICKET-030 (Smoke Test)
         │
    TICKET-031 (README)
         │
    TICKET-032 (E2E con APIs reales)
         │
    TICKET-033 (Modelo + Config BusinessContext)
    TICKET-034 (ContextAgent: scrape + resumen)
    TICKET-035 (QueryGeneratorAgent: LLM genera queries)
    TICKET-036 (Integrar en crew.py)
```

---

## Cronograma Sugerido (1 dev senior)

```
SEMANA 1                          SEMANA 2               SEMANA 3
│                                 │                       │
├─ Día 1 ── EP-0 completo         ├─ Día 6 ── EP-2b:     ├─ Día 11 ── EP-4:
│           (T001-T005)           │          Enrichment,  │            Crew Assembly
│                                 │          VisitTiming  │            (T024, T025)
├─ Día 2 ── EP-1a:                │          (T016, T017) │
│           Tavily, Brave, DDG,   │                       ├─ Día 12 ── EP-5:
│           Dedup (T006-008, T025)├─ Día 7 ── EP-2c:     │            Excel E2E,
│                                 │          Profiler     │            JSON Log
├─ Día 3 ── EP-1b:                │          (T018)       │            (T026, T027)
│           Maps, PopularTimes    │                       │
│           (T009, T010)          ├─ Día 8 ── EP-2d:     ├─ Día 13 ── EP-6:
│                                 │          Qualifier,   │            Tests, Smoke,
├─ Día 4 ── EP-1c:                │          Output       │            README
│           Scraper, Excel        │          (T019, T020) │            (T028-T031)
│           (T011, T012)          │
│                                 ├─ Día 9 ── EP-3:
├─ Día 5 ── EP-2a:                │          Todos los
│           Search, Maps,         │          Prompts
│           Scraper agents        │          (T021-T023)
│           (T013-T015)           │
│                                 ├─ Día 10 ── Buffer/
                                  │           review
```

---

## Registro de Riesgos

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|-------------|---------|------------|
| R1 | `popular_times` no disponible en Places API (New) | Alta | Medio | PopularTimesTool scraping HTML (T010) ya es el fallback |
| R2 | Google Maps bloquea Playwright scraping | Media | Medio | User-Agent rotation; rate limiting 3s entre scrapes |
| R3 | Bedrock throttling en batches grandes | Media | Bajo | Fallback OpenAI automático (T004) |
| R4 | CrewAI `Process.hierarchical` inestable con 8+ agentes | Baja | Alto | ✅ Resuelto: se usa flujo programático híbrido en `crew.py` |
| R5 | LLM genera JSON no parseable en ProfilerAgent | Media | Medio | `with_structured_output` + Pydantic validation + retry 1x |
| R6 | DuckDuckGo bloquea requests frecuentes | Alta | Bajo | Es solo modo dev; en prod se usa Tavily+Brave |
| R7 | Sites con Cloudflare bloquean Playwright | Media | Bajo | Skip y marcar como `scrape_failed = True` en el lead |

---

## 🚀 Próximos pasos (actualizado 2026-03-21)

### Completados ✅

| Ticket | Tarea |
|--------|-------|
| T027 | `output_agent.py` — `run_log_{timestamp}.json` generado |
| T030 | Smoke test infraestructura lista (venv, Chromium, .env, dry-run OK) |

### Activos / En progreso

| Ticket | Tarea | Prioridad |
|--------|-------|-----------|
| T031 | README para el equipo de ventas | P2 |
| T032 | E2E real con Tavily + Google Maps (necesita API keys) | P1 |

### Pendientes

| Ticket | Tarea | Prioridad |
|--------|-------|-----------|
| T026 | `test_excel_tool.py` — validación E2E del Excel con 20 leads | P0 |
| T029 | Tests de integración de agentes (LLM mockeado) | P1 |
| T033 | Modelo BusinessContext + YAML config (EP-7) | P1 |
| T034 | ContextAgent: scrape URLs + resumen del negocio | P1 |
| T035 | QueryGeneratorAgent: LLM genera queries automáticamente | P1 |
| T036 | Integrar EP-7 en crew.py (paso 0 del pipeline) | P1 |

### Estado del código (35 archivos creados) ✅

```
client_prospective_agents/
├── main.py              ✅  ├── crew.py              ✅
├── config.py            ✅  ├── llm_factory.py       ✅ (ChatBedrock bug fixed)
├── models.py            ✅  ├── search_config.yaml   ✅
├── requirements.txt     ✅  ├── .env.example         ✅
├── agents/ (8 archivos) ✅
├── tools/  (8 archivos) ✅  (dedup_tool.py sin crewai dep)
├── prompts/(4 archivos) ✅
├── tests/               ✅  55/55 tests pasando
└── output/.gitkeep      ✅
```

# Growth Guard — Sistema de Prospección de Leads B2B

Herramienta multi-agente que busca, enriquece y califica prospectos de negocios en Bogotá/Colombia, y los entrega en un Excel listo para que el equipo comercial empiece a contactar.

---

## Índice

1. [¿Qué hace el sistema?](#1-qué-hace-el-sistema)
2. [Requisitos](#2-requisitos)
3. [Instalación rápida](#3-instalación-rápida)
4. [Configurar variables de entorno](#4-configurar-variables-de-entorno)
5. [Configurar una campaña](#5-configurar-una-campaña)
6. [Ejecutar](#6-ejecutar)
7. [Entender el Excel](#7-entender-el-excel)
8. [Sistema de scoring](#8-sistema-de-scoring)
9. [Modo local sin API keys](#9-modo-local-sin-api-keys)
10. [Smoke test rápido](#10-smoke-test-rápido)
11. [Referencia de variables de entorno](#11-referencia-de-variables-de-entorno)
12. [Solución de problemas](#12-solución-de-problemas)

---

## 1. ¿Qué hace el sistema?

Dado un archivo YAML con el nombre de la campaña y las consultas de búsqueda, el sistema ejecuta automáticamente este pipeline:

```
Búsqueda web       Extracción   Dedup +          Perfilización    Excel
(Tavily, Brave, ─► (scraping ─► Enriquecimiento ─► + Calificación ─► output/
 Google Maps)       sitios web)  con IA)             (HOT/WARM/COLD)
```

**Resultado**: un archivo Excel con 5 hojas que incluye nombre, teléfono, email, sitio web, rating de Google, métricas de madurez digital, perfil de ventas (Hormozi / Challenger / Cardone), horarios de visita recomendados y el hook de pitch personalizado para cada negocio.

---

## 2. Requisitos

| Componente | Versión mínima |
|-----------|---------------|
| Python    | 3.10           |
| Sistema   | Linux / macOS / WSL2 Ubuntu |
| RAM       | 2 GB libres    |
| Disco     | 500 MB (Playwright Chromium) |

API keys necesarias para producción:

| API | Para qué se usa | Sin ella... |
|-----|----------------|-------------|
| `OPENAI_API_KEY` | Enriquecimiento, perfilado, calificación LLM | Sistema no funciona |
| `TAVILY_API_KEY` | Búsqueda web de negocios | Quita `tavily` de `sources` en config |
| `GOOGLE_MAPS_API_KEY` | Datos de Places (teléfono, rating, reseñas) | Quita `google_maps` de `sources` en config |
| `BRAVE_API_KEY` | Búsqueda web alternativa | Quita `brave` de `sources` en config |

---

## 3. Instalación rápida

```bash
cd ~/repositories/client_prospective_agents

# Crear entorno virtual con Python 3.10
python3.10 -m venv .venv
source .venv/bin/activate

# Instalar todas las dependencias
pip install -r requirements.txt

# Instalar navegador Chromium para scraping de Google Maps
playwright install chromium
```

---

## 4. Configurar variables de entorno

```bash
# Copiar la plantilla
cp .env.example .env

# Editar con tus claves
nano .env   # o cualquier editor de texto
```

Mínimo para el modo local (sin Google Maps ni Brave):

```dotenv
OPENAI_API_KEY=sk-...
```

Para producción completa:

```dotenv
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
GOOGLE_MAPS_API_KEY=AIza...
BRAVE_API_KEY=BSA...
```

---

## 5. Configurar una campaña

Edita o crea un archivo YAML. El archivo de ejemplo es `search_config.yaml`:

```yaml
campaign:
  name: "Talleres Bogotá Q1-2026"      # Nombre visible en el Excel y el log
  queries:
    - "taller mecánico Bogotá"          # Consultas de búsqueda (en español)
    - "mecánico automotriz chapinero"
  city: "Bogotá"
  country: "Colombia"
  language: "es"
  max_leads: 50                         # Máximo de leads a procesar
  sources:
    - google_maps                       # Fuentes activas
    - tavily
    # - brave
    # - duckduckgo                      # Sin API key — solo para desarrollo
  scrape_websites: true                 # Ir a los sitios web de los negocios
  scraper_concurrency: 5                # Scrapes simultáneos
  output_filename: "prospectos_talleres"

llm:
  provider: openai                      # openai | bedrock
  temperature: 0.2

qualification:
  min_score_hot: 7.0                    # Score ≥ 7 → HOT
  min_score_warm: 4.5                   # Score ≥ 4.5 → WARM (resto → COLD)
  target_hot_warm: 20                   # Reintentar si hay menos HOT+WARM
```

---

## 6. Ejecutar

```bash
# Activar el entorno virtual
source .venv/bin/activate

# Ejecutar con la config de campaña
python main.py --config search_config.yaml

# Opciones útiles
python main.py --config search_config.yaml --max-leads 30    # Limitar cantidad
python main.py --config search_config.yaml --llm openai      # Forzar OpenAI
python main.py --config search_config.yaml --llm bedrock     # Forzar AWS Bedrock
```

El sistema muestra progreso en consola y al finalizar indica dónde quedó el archivo Excel:

```
✅  Pipeline completado en 87s  →  output/prospectos_talleres_bogota_20260321_142503.xlsx
📋  Run log                    →  output/run_log_20260321_142503.json
```

---

## 7. Entender el Excel

El archivo tiene **5 hojas**:

| Hoja | Contenido | Color encabezado |
|------|-----------|-----------------|
| `HOT` | Leads prioritarios (score ≥ 7) | Rojo oscuro |
| `WARM` | Leads de interés medio (score 4.5–7) | Naranja |
| `COLD` | Leads de baja prioridad (score < 4.5) | Azul oscuro |
| `TODOS` | Todos los leads ordenados por prioridad | Gris/azul |
| `RESUMEN` | Totales, fuentes, duración del proceso | Verde oscuro |

### Grupos de columnas

#### Contacto
| Columna | Descripción |
|---------|-------------|
| Nombre | Nombre del negocio |
| Teléfono | Número principal |
| WhatsApp | Número de WhatsApp si fue detectado |
| Emails | Correos encontrados en el sitio web |
| Sitio Web | URL del sitio |

#### Ubicación
| Columna | Descripción |
|---------|-------------|
| Dirección | Dirección física |
| Ciudad | Ciudad de la campaña |

#### Datos Operativos
| Columna | Descripción |
|---------|-------------|
| Rating Google | Calificación en Google Maps (1–5) |
| Reseñas | Cantidad de reseñas en Google |
| Madurez Digital | `low` / `medium` / `high` — qué tan desarrollada está su presencia online |
| Stack Tech | Tecnologías detectadas (sistema POS, CRM, e-commerce, etc.) |
| Redes Sociales | Links a Facebook, Instagram, etc. |

#### Perfil
| Columna | Descripción |
|---------|-------------|
| Tamaño Est. | Estimado de empleados: `micro` / `small` / `medium` |
| Sector | Sector principal del negocio |
| Tipo Comprador | Perfil Challenger: `Skater`, `Friend`, `Teacher`, `Guide`, `Climber` |
| Score Hormozi | Puntuación 0–10 calculada con la fórmula de Alex Hormozi |
| Label Hormozi | Etiqueta: `STARVING_CROWD` / `HIGH_VALUE` / `ACCESSIBLE` / `WEAK_FIT` |
| Compromiso | Nivel de compromiso detectado según Grant Cardone |
| Canal Entrada | Canal de contacto recomendado por Cardone: `phone` / `visit` / `email` |
| Objeción Princ. | Principal objeción de ventas anticipada |
| Pitch Hook | Frase de apertura personalizada para el vendedor |
| Acción Propuesta | Primera acción concreta que debe tomar el vendedor |

#### Timing de Contacto
| Columna | Descripción |
|---------|-------------|
| Mejor Horario | Resumen en texto de las mejores horas para visitar o llamar |
| Conf. Horario | `high` (datos reales de Google) / `inferred` (estimado por IA) |

#### Score y Prioridad
| Columna | Descripción |
|---------|-------------|
| Score Final | Puntuación compuesta 0–10 |
| Tier | `HOT` / `WARM` / `COLD` |
| Prioridad | Orden de contacto: 1 = más urgente |
| Razón Descarte | Por qué quedó como COLD (si aplica) |

---

## 8. Sistema de scoring

El **Score Final** (0–10) combina cuatro frameworks de ventas:

```
Score = (Hormozi/10 × 35%)
      + (Challenger × 20%)
      + (Madurez digital inversa/10 × 15%)
      + (Rating/5 × 10%)
      + (Cardone × 20%)
```

### Score Hormozi (35% del total)

Mide el "hambre" del negocio de mejorar sus ventas. Se calcula sobre 4 dimensiones (cada una 0–3):

| Dimensión | Descripción |
|-----------|-------------|
| **Urgencia** | ¿El negocio tiene necesidad inmediata? |
| **Poder adquisitivo** | ¿Puede pagar el servicio de Growth Guard? |
| **Accesibilidad** | ¿Es fácil contactar al dueño/decisor? |
| **Fit de mercado** | ¿El servicio resuelve su problema real? |

Formula: `(urgencia + poder + accesibilidad + fit) × (10 / 12)`

> **HOT Hormozi** = `STARVING_CROWD` — negocio con urgencia alta, puede pagar, es accesible y está en mercado activo.

### Tipo Comprador Challenger (20%)

| Tipo | Descripción | Score |
|------|-------------|-------|
| `Skater` | No participa, pasa el tiempo | 0.0 |
| `Friend` | Simpático pero sin poder de decisión | 0.3 |
| `Teacher` | Abierto a aprender, toma acción | 0.8 |
| `Guide` | Conecta con el equipo, abre puertas | 0.7 |
| `Climber` | Usa la info para avanzar personalmente | 0.5 |

### Nivel Cardone (20%)

| Nivel | Descripción | Score |
|-------|-------------|-------|
| `low` | Sin interés ni señales | 0.2 |
| `medium` | Interés moderado, necesita empuje | 0.5 |
| `high` | Listo para actuar | 0.9 |
| `committed` | Ya tomó decisiones similares antes | 1.0 |

---

## 9. Modo local sin API keys

Para hacer pruebas sin gastar créditos de API:

```yaml
# En el archivo YAML de config:
sources:
  - duckduckgo   # Solo esta fuente — sin API key
```

```bash
python main.py --config tests/fixtures/smoke_config.yaml --max-leads 5 --llm openai
```

> **Nota**: DuckDuckGo puede retornar 0 resultados intermitentemente (bloqueo por rate limit). Si pasa, espera 1–2 minutos y reintenta, o usa Tavily con API key.

---

## 10. Smoke test rápido

Verifica que la instalación esté correcta:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
# Resultado esperado: 55 passed in < 2s

python main.py --config tests/fixtures/smoke_config.yaml --max-leads 5 --llm openai
# Resultado esperado: Excel + run_log generados en output/
```

Para el E2E completo con APIs reales (TICKET-032):

```bash
# Con TAVILY_API_KEY y GOOGLE_MAPS_API_KEY configurados en .env:
python main.py --config tests/fixtures/e2e_config.yaml --max-leads 20 --llm openai
```

---

## 11. Referencia de variables de entorno

| Variable | Obligatoria | Fuente de obtención |
|----------|-------------|---------------------|
| `OPENAI_API_KEY` | **Sí** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `TAVILY_API_KEY` | Solo si usas `tavily` | [app.tavily.com](https://app.tavily.com) |
| `GOOGLE_MAPS_API_KEY` | Solo si usas `google_maps` | Google Cloud Console → APIs & Services → Credentials |
| `BRAVE_API_KEY` | Solo si usas `brave` | [api.search.brave.com](https://api.search.brave.com) |
| `AWS_ACCESS_KEY_ID` | Solo si `provider: bedrock` | AWS IAM Console |
| `AWS_SECRET_ACCESS_KEY` | Solo si `provider: bedrock` | AWS IAM Console |
| `AWS_DEFAULT_REGION` | Solo si `provider: bedrock` | Default: `us-east-1` |
| `BEDROCK_MODEL_ID` | No | Default: `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `LLM_TEMPERATURE` | No | Default: `0.2` |

> Para que Google Maps API funcione, habilita en Google Cloud Console:  
> **Places API (New)** · **Maps JavaScript API**

---

## 12. Solución de problemas

### "0 leads encontrados" con DuckDuckGo
DuckDuckGo bloquea requests frecuentes. Espera 2–3 minutos y reintenta, o usa Tavily como fuente alternativa.

### Error `ImportError: crewai not found`
```bash
source .venv/bin/activate   # asegúrate de estar en el venv
pip install crewai>=0.80
```

### Error `playwright._impl._errors.Error: Executable doesn't exist`
```bash
playwright install chromium
```

### Error `ValidationError` en algún agente
El LLM devolvió un JSON inesperado. Aumenta `temperature` a 0.3 en el YAML o reduce `max_leads` para disminuir la carga por llamada.

### Los tiempos de visita muestran `timing_confidence: inferred`
El negocio no tiene datos de `popular_times` en Google Maps. La IA estimó los horarios basándose en el tipo de negocio y ciudad — es una aproximación, no datos reales.

### El Excel está vacío (hoja HOT y WARM sin filas)
Baja los umbrales en el YAML:
```yaml
qualification:
  min_score_hot: 6.0    # era 7.0
  min_score_warm: 3.5   # era 4.5
```

### Bedrock `ThrottlingException`
El sistema hace fallback automático a OpenAI. Si persiste, configura `provider: openai` directamente en el YAML.

---

*Generado automáticamente por Growth Guard Lead Prospecting Agents v1.0 — 2026-03-21*

# OAN Backend — Architecture & Design

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                     │
│   Frontend (React)  ──  98.90.156.237.nip.io                       │
│   Mobile App        ──  WebSocket / REST                            │
└────────────┬──────────────────┬──────────────────┬──────────────────┘
             │ REST/SSE         │ WebSocket         │ REST
             ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI (8 Uvicorn workers)                       │
│                    Port 8000 via Supervisor                          │
├─────────────┬──────────┬──────────┬──────────┬──────────┬───────────┤
│ /api/chat/  │/api/conv/│/api/tts/ │/api/     │/api/     │/api/      │
│  (SSE)      │ (WS)     │          │transcribe│suggest/  │health/    │
└──────┬──────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┴───────────┘
       │           │          │          │          │
       ▼           ▼          ▼          ▼          ▼
   Chat Flow   Voice Flow   TTS      STT       Suggestions
```

---

## Sequence Diagram — Text Chat (Primary Flow)

```
User                Frontend            Chat Router          Chat Service         FastGeminiService        OpenRouter         Tools              Redis       PostgreSQL
  │                    │                     │                    │                      │                    │                │                  │              │
  │─── "oxen price    ─┼────POST /api/chat/──┤                    │                      │                    │                │                  │              │
  │     in Dubti?"     │                     │                    │                      │                    │                │                  │              │
  │                    │                     │──get history──────►│                      │                    │                │──GET {sid}_oan──►│              │
  │                    │                     │                    │                      │                    │                │◄─ history ───────│              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │                     │──stream_chat_msgs─►│                      │                    │                │                  │              │
  │                    │                     │                    │──1. PII mask─────────┤                    │                │                  │              │
  │                    │                     │                    │──2. Create context───┤                    │                │                  │              │
  │                    │                     │                    │──3. Trim history─────┤                    │                │                  │              │
  │                    │                     │                    │──4. generate_resp()─►│                    │                │                  │              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │                     │                    │                      │──chat.completions──►                │                  │              │
  │                    │                     │                    │                      │  (stream + tools)  │                │                  │              │
  │                    │                     │                    │                      │◄─tool_call: ───────│                │                  │              │
  │                    │                     │                    │                      │  livestock_price   │                │                  │              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │                     │                    │                      │──execute_tool()───────────────────►│                  │              │
  │                    │                     │                    │                      │                    │                │──SQL query──────────────────────►
  │                    │                     │                    │                      │                    │                │◄─ price data ───────────────────│
  │                    │                     │                    │                      │◄─tool result───────────────────────│                  │              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │                     │                    │                      │──chat.completions──►                │                  │              │
  │                    │                     │                    │                      │  (with tool result)│                │                  │              │
  │                    │                     │                    │                      │◄─streamed text─────│                │                  │              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │◄─────SSE chunks─────┼◄───yield text──────┼◄─yield tokens───────┤                    │                │                  │              │
  │◄── render ─────────│                     │                    │                      │                    │                │                  │              │
  │                    │                     │                    │──5. Update history──►│                    │                │──SET {sid}_oan──►│              │
  │                    │                     │                    │                      │                    │                │                  │              │
  │                    │                     │──background task───┤                      │                    │                │                  │              │
  │                    │                     │  (suggestions)     │                      │                    │                │                  │              │
```

---

## Component Map

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           DOCKER NETWORK (oan_network)                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                    oan_backend (deploy-backend)                   │     │
│  │                                                                   │     │
│  │  ┌──────────────┐   ┌──────────────────┐   ┌────────────────┐   │     │
│  │  │  Routers     │   │  Services         │   │  Agents        │   │     │
│  │  │              │   │                    │   │  (pydantic-ai) │   │     │
│  │  │  chat.py     │──►│  chat.py           │──►│  agrinet.py    │   │     │
│  │  │  suggest.py  │   │  fast_gemini.py    │   │  suggestions.py│   │     │
│  │  │  tts.py      │──►│  providers/tts.py  │   │  models.py     │   │     │
│  │  │  transcribe  │──►│  providers/stt.py  │   │  deps.py       │   │     │
│  │  │  conv.py (WS)│──►│  pipecat_pipeline  │   └───────┬────────┘   │     │
│  │  │  health.py   │   │  pii_masker.py     │           │            │     │
│  │  └──────────────┘   │  moderation.py     │   ┌───────▼────────┐   │     │
│  │                      └──────────────────┘   │  24 Tools       │   │     │
│  │                                              │                  │   │     │
│  │  ┌──────────────┐                           │  crop.py         │   │     │
│  │  │  Helpers      │                           │  Livestock.py    │   │     │
│  │  │  utils.py     │                           │  MarketPlace.py  │   │     │
│  │  │  amharic.py   │                           │  weather_tool.py │   │     │
│  │  │  tts.py       │                           │  maps.py         │   │     │
│  │  └──────────────┘                           │  rag_router.py   │   │     │
│  │                                              │  search_cosdata  │   │     │
│  │  ┌──────────────┐                           │  Regions.py      │   │     │
│  │  │  Scrapers     │                           │  scheme.py       │   │     │
│  │  │  sync_crops   │                           │  terms.py        │   │     │
│  │  │  sync_prices  │                           └──────────────────┘   │     │
│  │  │  sync_market  │                                                   │     │
│  │  │  sync_livest  │                                                   │     │
│  │  └──────────────┘                                                   │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│           │              │                │               │              │
│           ▼              ▼                ▼               ▼              │
│  ┌──────────────┐ ┌───────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ oan_postgres  │ │ oan_redis │ │ oan_cosdata   │ │ oan_frontend │      │
│  │ postgres:15   │ │ redis:7   │ │ cosdata:latest│ │ nginx        │      │
│  │ Port 5432     │ │ Port 6379 │ │ Port 8443     │ │ Port 80/443  │      │
│  │               │ │           │ │               │ │              │      │
│  │ Tables:       │ │ Keys:     │ │ Collections:  │ │ Proxy → :8000│      │
│  │  marketplaces │ │  sessions │ │  oan-collection│ │              │      │
│  │  crops        │ │  suggest  │ │  (47 docs)    │ └──────────────┘      │
│  │  livestock    │ │  weather  │ │               │                       │
│  │  market_prices│ │  geocode  │ │ 1024-dim vecs │                       │
│  │  crop_variety │ │  prices   │ │ (multilingual │                       │
│  │  livestock_br │ │           │ │  -e5-large)   │                       │
│  │  scraper_logs │ │           │ │               │                       │
│  └──────────────┘ └───────────┘ └──────────────┘                       │
└──────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
         ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
         │   OpenRouter     │ │  Nominatim   │ │ OpenWeatherMap   │
         │   (LLM API)      │ │  (Geocoding) │ │ (Weather API)    │
         │                  │ │              │ │                  │
         │ qwen/qwen3.5-   │ │ 74.225.15.164│ │ api.openweather  │
         │ flash-02-23      │ │ (self-hosted)│ │ map.org          │
         └──────────────────┘ └──────────────┘ └──────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │  NMIS API        │
         │  nmis.et/api/    │
         │  (Ethiopian      │
         │   market data)   │
         │  ─── scraped ──► │
         │  into PostgreSQL  │
         └──────────────────┘
```

---

## API Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/chat/` | POST | Text chat with tool calling | SSE stream (JSON chunks) |
| `/api/conv/ws` | WebSocket | Real-time voice conversation | Audio frames |
| `/api/tts/` | POST | Text-to-speech | Base64 audio |
| `/api/transcribe/` | POST | Speech-to-text | Transcribed text |
| `/api/suggest/` | POST | Follow-up suggestions | List of questions |
| `/api/health/live` | GET | Liveness probe | 200 OK |
| `/api/health/ready` | GET | Readiness probe | Redis status |
| `/api/health/` | GET | Full health check | Dependencies + uptime |

---

## Chat Pipeline Stages

```
User Query
  │
  ├─► 1. PII Masking        (phone, email, Aadhaar, bank accounts)
  ├─► 2. Context Prep        (FarmerContext: query, lang_code)
  ├─► 3. History Trim        (60k token limit, last N message pairs)
  ├─► 4. Pre-Moderation      (optional — hate speech / prompt injection)
  ├─► 5. FastGeminiService   (OpenAI-compatible API → OpenRouter)
  │     ├─► LLM call with 12 tool schemas
  │     ├─► Tool execution loop (max 5 rounds)
  │     └─► Stream text tokens back
  ├─► 6. Source Extraction    (collect tool data sources)
  ├─► 7. History Update       (save to Redis)
  └─► 8. Background Task      (generate suggestions)
```

---

## Voice Conversation Flow (WebSocket)

```
Client (mic)        WebSocket           Pipecat Pipeline
    │                  │                      │
    │── audio frames ─►│──► FasterWhisperSTT ─┤
    │                  │    (VAD + batch)      │
    │                  │                      ├──► AgriNetLLMService
    │                  │                      │    (OpenRouter + tools)
    │                  │                      │         │
    │                  │                      │    ◄────┘ text response
    │                  │                      │
    │                  │                      ├──► CoquiXTTSProvider
    │                  │                      │    (text → audio)
    │◄─ audio frames ──┤◄─────────────────────┘
    │   (speaker)      │
```

---

## Agent System (Pydantic-AI)

### agrinet_agent (Main Chat Agent)
- **Model:** OpenRouter (`qwen/qwen3.5-flash-02-23`)
- **Output:** `str`
- **Temperature:** 0.2
- **Tools:** 24 tools (see below)
- **System prompt:** Dynamic, language-aware (English / Amharic)
- **End strategy:** exhaustive

### generation_agent (Phase 2 — No Tools)
- Same model, no tools, for synthesizing final answers from tool context

### suggestions_agent (Background)
- **Output:** `str` (parsed to list)
- **Tools:** `search_documents` only
- Generates 3–5 follow-up questions in target language

---

## Tool Inventory (24 Tools)

### Market Price Tools
| Tool | File | Purpose | Cache TTL |
|------|------|---------|-----------|
| `get_crop_price_quick` | `agents/tools/crop.py` | Price by crop + marketplace name | 15 min |
| `get_livestock_price_quick` | `agents/tools/Livestock.py` | Price by livestock + marketplace | 15 min |
| `list_crops_in_marketplace` | `agents/tools/crop.py` | All crops at a marketplace | 1 hour |
| `list_livestock_in_marketplace` | `agents/tools/Livestock.py` | All livestock at a marketplace | 1 hour |
| `get_crop_price_in_marketplace` | `agents/tools/crop.py` | Detailed crop price | 15 min |
| `get_livestock_price_in_marketplace` | `agents/tools/Livestock.py` | Detailed livestock price | 15 min |
| `compare_crop_prices_nearby` | `agents/tools/crop.py` | Compare across nearby markets | 15 min |
| `compare_livestock_prices_nearby` | `agents/tools/Livestock.py` | Compare across nearby markets | 15 min |

### Marketplace Tools
| Tool | File | Purpose |
|------|------|---------|
| `list_active_crop_marketplaces` | `agents/tools/MarketPlace.py` | All crop marketplace names (En + Am) |
| `list_active_livestock_marketplaces` | `agents/tools/MarketPlace.py` | All livestock marketplace names |
| `list_crop_marketplaces_by_region` | `agents/tools/MarketPlace.py` | Filter by region |
| `list_livestock_marketplaces_by_region` | `agents/tools/MarketPlace.py` | Filter by region |
| `find_crop_marketplace_by_name` | `agents/tools/MarketPlace.py` | Marketplace details by name |
| `find_livestock_marketplace_by_name` | `agents/tools/MarketPlace.py` | Marketplace details by name |
| `find_nearest_crop_marketplaces` | `agents/tools/MarketPlace.py` | Closest markets by coordinates |
| `find_nearest_livestock_marketplaces` | `agents/tools/MarketPlace.py` | Closest markets by coordinates |

### Weather Tools
| Tool | File | External Service |
|------|------|------------------|
| `get_current_weather` | `agents/tools/weather_tool.py` | OpenWeatherMap API |
| `get_weather_forecast` | `agents/tools/weather_tool.py` | OpenWeatherMap API |

### Geolocation Tools
| Tool | File | External Service |
|------|------|------------------|
| `forward_geocode` | `agents/tools/maps.py` | Nominatim (self-hosted) |
| `reverse_geocode` | `agents/tools/maps.py` | Nominatim (self-hosted) |

### RAG / Knowledge Base Tools
| Tool | File | External Service |
|------|------|------------------|
| `search_documents` | `agents/tools/rag_router.py` | Cosdata (or Marqo) |
| `search_terms` | `agents/tools/terms.py` | Marqo |
| `get_scheme_info` | `agents/tools/scheme.py` | Marqo |

### Region Detection
| Tool | File | Data Source |
|------|------|------------|
| `detect_crop_region` | `agents/tools/Regions.py` | PostgreSQL |
| `detect_livestock_region` | `agents/tools/Regions.py` | PostgreSQL |

---

## Database Schema (PostgreSQL — `load_agri`)

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  marketplaces    │     │  crops           │     │  livestock       │
├──────────────────┤     ├──────────────────┤     ├──────────────────┤
│  marketplace_id  │◄──┐ │  crop_id         │◄──┐ │  livestock_id    │◄──┐
│  name            │   │ │  name            │   │ │  name            │   │
│  name_amharic    │   │ │  name_amharic    │   │ │  name_amharic    │   │
│  marketplace_type│   │ │  category        │   │ │  category        │   │
│  region          │   │ │  unit            │   │ │  unit            │   │
│  latitude        │   │ │  is_active       │   │ │  is_active       │   │
│  longitude       │   │ └──────────────────┘   │ └──────────────────┘   │
│  is_active       │   │                        │                        │
└──────────────────┘   │ ┌──────────────────┐   │ ┌──────────────────┐   │
                       │ │  crop_varieties  │   │ │  livestock_breeds│   │
                       │ ├──────────────────┤   │ ├──────────────────┤   │
                       │ │  variety_id      │   │ │  breed_id        │   │
                       │ │  crop_id ────────┘   │ │  livestock_id ───┘   │
                       │ │  name            │   │ │  name            │   │
                       │ │  name_amharic    │   │ │  name_amharic    │   │
                       │ └──────────────────┘   │ └──────────────────┘   │
                       │                        │                        │
                       │ ┌──────────────────────┴────────────────────┐   │
                       │ │  market_prices                            │   │
                       │ ├──────────────────────────────────────────┤   │
                       └─┤  marketplace_id                          │   │
                         │  crop_id / livestock_id ─────────────────┘   │
                         │  min_price, max_price, avg_price             │
                         │  modal_price, currency                       │
                         │  price_date                                  │
                         └──────────────────────────────────────────────┘

┌──────────────────┐
│  scraper_logs    │
├──────────────────┤
│  scraper_type    │
│  status          │
│  started_at      │
│  completed_at    │
│  records_fetched │
│  records_inserted│
│  records_updated │
│  error_message   │
└──────────────────┘
```

**Current Counts:**
| Table | Records |
|-------|---------|
| marketplaces | 331 (309 crop + 22 livestock) |
| crops | 19 |
| livestock | 30 |
| crop_varieties | 26 |
| livestock_breeds | 76 |
| market_prices | 4,946 |

---

## Caching Strategy (Redis)

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `{session_id}_oan` | 24h | Conversation message history |
| `suggestions_{session_id}_{lang}` | 30 min | Follow-up suggestion lists |
| `weather:current:{lat}:{lon}:{units}` | 15 min | Current weather data |
| `geocode:forward:{place}` | 24h | Geocoding results |
| `geocode:reverse:{lat}:{lon}` | 24h | Reverse geocoding results |
| `{marketplace}:{item}:{date}` | 15 min | Market price lookups |

---

## Data Ingestion (Scrapers)

**Source:** NMIS API (`nmis.et/api/`) — Ethiopian National Market Information System

```
run_all_scrapers.py
  │
  ├─► sync_marketplaces.py      309 crop + 22 livestock locations
  ├─► sync_crops.py             19 crop types
  ├─► sync_livestock.py         30 livestock types
  ├─► sync_crop_varieties.py    26 varieties
  ├─► sync_livestock_varieties  76 breeds
  ├─► sync_crop_prices.py       Daily crop prices → market_prices
  ├─► sync_livestock_prices.py  Daily livestock prices → market_prices
  ├─► sync_crop_prices_table    Latest prices with collected_at dates
  └─► sync_livestock_prices_tbl Latest prices with collected_at dates
```

**Execution:** `docker exec oan_backend python scripts/run_all_scrapers.py`
**Duration:** ~27 minutes for full sync

---

## RAG / Vector Search (Cosdata)

- **Collection:** `oan-collection`
- **Documents:** 47 agricultural knowledge base docs
- **Embedding model:** `intfloat/multilingual-e5-large` (1024 dimensions)
- **Source file:** `assets/all_agricultural_docs.json`
- **Distance metric:** cosine
- **Index:** HNSW (ef_construction=128, ef_search=64)

**Indexing:**
```bash
docker exec oan_backend python /tmp/run_index.py
# (requires typing.Self patch for Python 3.10)
```

---

## External Service Dependencies

| Service | Purpose | Config | Auth |
|---------|---------|--------|------|
| **OpenRouter** | LLM inference | `LLM_PROVIDER=openrouter` | `OPENROUTER_API_KEY` |
| **PostgreSQL** | Market data storage | `DATABASE_URL` | user/password |
| **Redis** | Session cache + rate data | `REDIS_HOST:REDIS_PORT` | None |
| **Cosdata** | Vector DB for RAG | `COSDATA_ENDPOINT_URL` | username/password |
| **Nominatim** | Geocoding (self-hosted) | `NOMINATIM_DOMAIN` | None |
| **OpenWeatherMap** | Weather data | `OPENWEATHERMAP_API_KEY` | API key |
| **NMIS API** | Ethiopian market data | Hardcoded base URL | None |
| **Faster-Whisper** | Speech-to-text | `FASTER_WHISPER_URL` | None |
| **Coqui XTTS** | Text-to-speech | `XTTS_URL` | None |
| **Azure Cognitive** | Fallback STT/TTS | `azure_foundary_api_key` | API key |

---

## Docker Infrastructure

| Container | Image | Port | Volumes |
|-----------|-------|------|---------|
| `oan_backend` | `deploy-backend` (built) | 8000 | App source mounted |
| `oan_frontend` | `deploy-frontend` (built) | 80/443 | Nginx config |
| `oan_postgres` | `postgres:15-alpine` | 5432 | `postgres_data` |
| `oan_redis` | `redis:7-alpine` | 6379 | `redis_data` |
| `oan_cosdata` | `cosdatateam/cosdata` | 8443, 50051 | `cosdata_data` |

**Network:** `oan_network` (bridge) — all containers communicate via service names

---

## Key Data Flows Summary

| Flow | Path | Services Hit |
|------|------|-------------|
| **Text Chat** | Router → ChatService → FastGeminiService → OpenRouter (+ tools → PG) | OpenRouter, PostgreSQL, Redis |
| **Voice Chat** | WebSocket → Pipecat → STT → LLM → TTS → WebSocket | Faster-Whisper, OpenRouter, XTTS |
| **RAG Search** | Tool call → rag_router → Cosdata → embedding search | Cosdata, HuggingFace |
| **Market Prices** | Tool call → crop.py / Livestock.py → PostgreSQL | PostgreSQL, Redis (cache) |
| **Weather** | Tool call → weather_tool.py → OpenWeatherMap | OpenWeatherMap |
| **Geocoding** | Tool call → maps.py → Nominatim | Nominatim |
| **Data Sync** | run_all_scrapers.py → NMIS API → PostgreSQL | NMIS API, PostgreSQL |
| **Suggestions** | Background task → suggestions_agent → OpenRouter | OpenRouter, Redis |

---

## Configuration Hierarchy

```
.env (secrets, provider selection)
  │
  ▼
app/config.py (Settings class — validates & loads)
  │
  ▼
Module-level imports (agents/models.py, services/fast_gemini.py, etc.)
```

**Key Environment Variables:**
- `LLM_PROVIDER` / `LLM_MODEL_NAME` — LLM backend selection
- `RAG_PROVIDER` — Vector DB choice (`cosdata` or `marqo`)
- `STT_PROVIDER` / `TTS_PROVIDER` — Voice service selection
- `DATABASE_URL` — PostgreSQL connection string
- `ENABLE_MODERATION` — Toggle content safety checks
- `SCRAPER_ENABLED` — Toggle data ingestion on startup

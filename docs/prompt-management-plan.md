# Prompt Management Implementation Plan

## Status: In Progress

---

## What's Done

| File | Status | Notes |
|---|---|---|
| `app/prompts/__init__.py` | Created | Package init, singleton export for `PromptRegistry` |
| `app/prompts/models.py` | Created | `Prompt` + `PromptUsageLog` SQLAlchemy ORM models |
| `alembic/versions/a1b2c3d4e5f6_add_prompts_tables.py` | Created | Migration with tables, indexes, partial unique index |

---

## What Remains (in order)

### Step 1: Create `app/prompts/registry.py` — PromptRegistry class

The core singleton. Methods needed:

| Method | Sync/Async | Purpose |
|---|---|---|
| `get(name, lang, variant, context, session_id)` | async | Primary lookup: memory → Redis → DB → filesystem fallback |
| `get_sync(name, lang, variant, context)` | sync | For PydanticAI `@system_prompt` decorators (reads from `_memory_cache` only) |
| `get_json(name, lang, variant)` | async | Returns parsed JSON (for tool definitions like `OPENAI_TOOLS`) |
| `create_version(name, lang, content, ...)` | async | Insert new draft version |
| `activate(name, version, lang, variant)` | async | Set version active, archive current active |
| `rollback(name, lang, variant)` | async | Reactivate previous version |
| `warm_cache()` | async | Called at startup — loads all active prompts into Redis + `_memory_cache` dict |

**Lookup chain:** `_memory_cache` dict → Redis (`oan-prompt:{name}:{lang}:{variant}`, 5 min TTL) → PostgreSQL (`WHERE status='active'`) → filesystem fallback via `helpers/utils.py:get_prompt()`.

**Key design decisions:**
- `warm_cache()` populates both Redis and `_memory_cache` at startup
- `get_sync()` reads from `_memory_cache` only — never blocks
- Usage logging via fire-and-forget `asyncio.create_task` (no latency on hot path)
- Jinja2 rendering happens at read time when `context` is provided
- Use existing `app/core/cache.py` Redis instance (`from app.core.cache import cache`)
- Use existing `app/database.py` session factory (`from app.database import get_db_session`)

---

### Step 2: Create `app/prompts/schemas.py` — Pydantic schemas

Request/response models for the admin API:

```
PromptCreate       — name, lang, content, content_type, description, template_vars, variant
PromptResponse     — all fields from DB model
PromptListResponse — list of PromptResponse with pagination
PromptActivate     — version number to activate
```

---

### Step 3: Create `app/prompts/seed.py` + `scripts/seed_prompts.py` — Seed script

Idempotent seeder that inserts v1 `status='active'` rows:

| DB name | Source | lang | content_type |
|---|---|---|---|
| `system_prompt` | `assets/prompts/en.md` | `en` | text |
| `system_prompt` | `assets/prompts/am.md` | `am` | text |
| `moderation_system` | `assets/prompts/moderation_system.md` | `*` | text |
| `moderation_fast` | `MODERATION_PROMPT` in `fast_gemini.py:17-35` | `*` | text |
| `suggestions_system` | `assets/prompts/suggestions_system.md` | `*` | text |
| `generation` | `assets/prompts/generation_en.md` | `en` | text |
| `agrinet_system` | `assets/prompts/agrinet_system.md` | `mr` | text |
| `openai_tools` | `OPENAI_TOOLS` in `fast_gemini.py:38-119` | `*` | json |
| `forbidden_phrases` | `instructions` in `llm.py:104-117` | `*` | text |

`scripts/seed_prompts.py` is a CLI entry: `python scripts/seed_prompts.py`

---

### Step 4: Wire up startup + config

**`app/config.py`** — add:
```python
prompt_cache_ttl: int = 300  # 5 minutes
```

**`main.py`** — add to `lifespan()` startup block (after cache health check):
```python
from app.prompts import get_prompt_registry
registry = get_prompt_registry()
await registry.warm_cache()
logger.info("Prompt registry warmed")
```

**`alembic/env.py`** — add import:
```python
from app.prompts.models import Prompt, PromptUsageLog
```

---

### Step 5: Swap consumers (one at a time)

#### 5a. `agents/suggestions.py` (line 14)
```python
# Before
system_prompt=get_prompt('suggestions_system')
# After
from app.prompts import prompt_registry
system_prompt=prompt_registry.get_sync('suggestions_system')
```

#### 5b. `agents/moderation.py` (line 27)
```python
# Before
system_prompt=get_prompt('moderation_system')
# After
from app.prompts import prompt_registry
system_prompt=prompt_registry.get_sync('moderation_system')
```

#### 5c. `agents/agrinet.py` (lines 23-28, 45-55)
Both `@system_prompt` decorators:
```python
# Before
return get_prompt(lang, context={'today_date': today_date})
# After
return prompt_registry.get_sync('system_prompt', lang=lang, context={'today_date': today_date})
```
Generation fallback:
```python
# Before
return get_prompt(f"generation_{lang}", context={'today_date': today_date})
# After
return prompt_registry.get_sync('generation', lang=lang, context={'today_date': today_date})
```

#### 5d. `app/services/fast_gemini.py`
- Line 154: `MODERATION_PROMPT` → `await prompt_registry.get('moderation_fast')`
- Line 228: `OPENAI_TOOLS` → `await prompt_registry.get_json('openai_tools')`
- Line 191: `get_prompt(lang, ...)` → `prompt_registry.get_sync('system_prompt', lang=lang, context={...})`

#### 5e. `app/services/providers/llm.py` (lines 104-117)
```python
# Before
instructions = ("⚠️ FORBIDDEN PHRASES...")
# After
from app.prompts import prompt_registry
instructions = prompt_registry.get_sync('forbidden_phrases')
```

---

### Step 6: Create `app/routers/prompts.py` — Admin API

Endpoints (JWT-protected):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/prompts/` | List prompts (filter by name, lang, status) |
| `GET` | `/api/prompts/{name}` | Get active version |
| `GET` | `/api/prompts/{name}/versions` | Version history |
| `POST` | `/api/prompts/{name}/versions` | Create new draft |
| `POST` | `/api/prompts/{name}/versions/{v}/activate` | Activate version (archives current) |
| `POST` | `/api/prompts/{name}/rollback` | Rollback to previous |

Wire into `main.py`:
```python
from app.routers.prompts import router as prompts_router
app.include_router(prompts_router, prefix=settings.api_prefix)
```

---

### Step 7: Cleanup

- Delete `MODERATION_PROMPT` constant from `fast_gemini.py` (lines 16-35)
- Delete `OPENAI_TOOLS` constant from `fast_gemini.py` (lines 37-119)
- Delete hardcoded `instructions` string from `llm.py` (lines 103-117)
- Keep `assets/prompts/*.md` — still used as seed source + filesystem fallback
- Keep `helpers/utils.py:get_prompt()` — used as final fallback in registry

---

## Verification Checklist

- [ ] `alembic upgrade head` — tables created
- [ ] `python scripts/seed_prompts.py` — 9 prompts seeded as v1 active
- [ ] `registry.get('system_prompt', lang='en')` returns same content as `assets/prompts/en.md`
- [ ] `POST /api/chat` works unchanged (integration test)
- [ ] Create v2 of `moderation_fast`, activate, verify served; rollback to v1, verify
- [ ] Redis key `oan-prompt:system_prompt:en:default` exists after `warm_cache()`
- [ ] In-memory fallback works when Redis is down

---

## Architecture Diagram

```
Consumer Code (agents, fast_gemini, llm.py)
        │
        ▼
   PromptRegistry  ← single entry point
        │
   ┌────┴────┐
   ▼         ▼
 Redis    PostgreSQL     ← cache (5 min TTL) / source of truth
   │         │
   └────┬────┘
        ▼
   assets/prompts/*.md   ← filesystem fallback + seed source
```

## Files Summary

### Already Created
| File | Purpose |
|---|---|
| `app/prompts/__init__.py` | Package init, singleton export |
| `app/prompts/models.py` | Prompt + PromptUsageLog ORM models |
| `alembic/versions/a1b2c3d4e5f6_add_prompts_tables.py` | Migration |

### Still Need to Create
| File | Purpose |
|---|---|
| `app/prompts/registry.py` | PromptRegistry class (Step 1) |
| `app/prompts/schemas.py` | Pydantic schemas for admin API (Step 2) |
| `app/prompts/seed.py` | DB seeder logic (Step 3) |
| `scripts/seed_prompts.py` | CLI entry for seeding (Step 3) |
| `app/routers/prompts.py` | Admin CRUD endpoints (Step 6) |

### Still Need to Modify
| File | Change |
|---|---|
| `app/config.py` | Add `prompt_cache_ttl` setting (Step 4) |
| `main.py` | Add `warm_cache()` to lifespan startup (Step 4) |
| `alembic/env.py` | Import new models (Step 4) |
| `agents/suggestions.py` | Use `registry.get_sync()` (Step 5a) |
| `agents/moderation.py` | Use `registry.get_sync()` (Step 5b) |
| `agents/agrinet.py` | Use `registry.get_sync()` (Step 5c) |
| `app/services/fast_gemini.py` | Remove constants, use registry (Step 5d + 7) |
| `app/services/providers/llm.py` | Remove hardcoded instructions, use registry (Step 5e + 7) |

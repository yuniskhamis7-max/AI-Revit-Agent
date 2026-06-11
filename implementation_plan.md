# ##############################################################
# SYSTEM REFACTORING PLAN: BACKEND SIMPLIFICATION & SOC
# ##############################################################

This document outlines the final plan to simplify the backend codebase, remove obsolete features, eliminate the ORM overhead, and restructure the backend into clean, decoupled layers.

---

## 1. ARCHITECTURAL LAYERS & SOC RULES

We will reorganize the codebase into three distinct directories:

```
  [ Presentation/API Layer (backend/api/) ]
                      │
                      │  Pure JSON-serializable Python Dictionaries
                      ▼
  [ Core Domain Layer (backend/core/) ]
                      │
                      │  Pure JSON-serializable Python Dictionaries
                      ▼
  [ Infrastructure Layer (backend/infra/) ] (db.py & revit_bridge.py)
```

### ### CORE DESIGN & CODING RULES:
1. **Decoupled & Agnostic Layers**: Layers must communicate **strictly** using standard Python JSON-serializable dictionaries (or `TypedDict` for type safety). No database classes, SQLAlchemy models, FastAPI request objects, or SSE event strings are allowed to cross layer boundaries.
2. **No Over-Crossreferencing**: Maintain a strict one-way dependency chain: `API` -> `Core` -> `Infrastructure`. No circular imports or cross-referencing allowed.
3. **OOP & Simplicity**: Prioritize Object-Oriented Programming (OOP) for primary structural entities (e.g., `Database`, `Agent`, and `AIProvider` instances) to keep the API clean.
4. **No ORM Magic**: The database will use pure SQL statements via a single unified Database utility class (`backend/infra/db.py`), eliminating the complexity of SQLAlchemy.

---

## 2. FEATURE SCOPE: WHAT IS KEPT AND REMOVED

### ### FEATURE A (AI Providers) -> GEMINI ONLY (Extensible)
- **Status**: **SIMPLIFIED**.
- **Action**: Keep only `gemini.py` and `base.py`. Remove `openai.py`, `anthropic.py`, `groq.py`, `openrouter.py`, `openai_compat.py`.
- **Rule**: Keep the provider factory in `providers/__init__.py` pluggable so re-adding other models in the future requires minimal effort.

### ### FEATURE B (Approval Gate) -> REMOVED (With Stop Support)
- **Status**: **REMOVED**.
- **Action**: Delete the block-and-wait approval popup mechanism (`ApprovalGate`, `/api/chat/approve` endpoint). The agent will immediately execute tools.
- **Halt Execution**: If the user clicks the "Stop" button in the frontend:
  1. The client aborts the HTTP request.
  2. The FastAPI server cancels the generator task.
  3. The API's `finally` block catches this and immediately commits/saves all generated messages and tool outputs up to that point.

### ### FEATURE C (Dynamic Tools) -> KEPT
- **Status**: **KEPT**.
- **Action**: Keep dynamic tool discovery via the `/api/revit/status` health check. Schemas remain dynamic and are queried from the Revit bridge.

### ### FEATURE D (Development Mocks) -> REMOVED (With Offline Warning)
- **Status**: **REMOVED**.
- **Action**: Delete simulated bridge mock responses in `revit_bridge.py`.
- **Non-crashing Startup**: Startup initialization in `main.py` will log a warning instead of throwing an exception if Revit is down.
- **Frontend Indicator**: Display a warning banner at the top of the chat area (`ChatWindow.tsx`) when the connection is disconnected.

---

## 3. PROPOSED REFACTORING CHECKS

### ### Phase 1: Database & Provider Clean Up
1. Write [db.py](file:///d:/Construction/Projects/ai_revit_agent/backend/infra/db.py) using `aiosqlite` and raw SQL.
2. Delete `backend/database.py`, `backend/models.py`, and `backend/migrations.py`.
3. Update `backend/requirements.txt` to remove SQLAlchemy.
4. Clean up `backend/providers/` to delete obsolete providers.

### ### Phase 2: Core Agent Loop Extrication
1. Create [agent_loop.py](file:///d:/Construction/Projects/ai_revit_agent/backend/core/agent_loop.py).
2. Rewrite the loop to accept standard JSON-serializable list of message dictionaries and yield JSON event dicts.

### ### Phase 3: Router Simplification
1. Refactor `backend/api/chat.py` to use `db.py` and `agent_loop.py`.
2. Refactor `backend/api/sessions.py`, `backend/api/providers.py`, and `backend/api/settings.py` to consume the new `Database` class.

### ### Phase 4: Frontend Warnings
1. Render a warning banner in `ChatWindow.tsx` if `revitStatus` is `'disconnected'`.

---




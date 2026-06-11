# Autodesk Revit AI Agent: Developer Learning Map

Welcome! This document outlines a structured, step-by-step learning path to help you understand, navigate, and contribute to the Revit AI Agent codebase. 

Because of the hybrid nature of this project (combining a React web interface, a FastAPI server, a C# bridge, and an IronPython plugin inside a desktop application), it is highly recommended to study the code in a specific sequence rather than jumping straight into the UI or the AI layers.

---

## The Core Study Path at a Glance

```
Milestone 1: Revit Integration & Marshaling (bridge-source/ & extension/)
    │
    ▼
Milestone 2: Backend Infrastructure & Discovery (backend/infra/ & backend/services/)
    │
    ▼
Milestone 3: Core AI Orchestration (backend/core/ & backend/providers/)
    │
    ▼
Milestone 4: Presentation & Event Streaming (backend/api/ & backend/main.py)
    │
    ▼
Milestone 5: React Frontend & Zustand State (frontend/src/)
```

---

## Milestone 1: The Revit Integration & C# Bridge (The Foundation)
Revit's single-threaded nature is the primary architectural constraint of the system. You must understand how work is marshaled across threads before studying anything else.

### Study Order & Files:
1. **[BridgeServer.cs](file:///d:/Construction/Projects/ai_revit_agent/bridge-source/BridgeServer.cs)**:
   * **Why**: This contains the threading core. Study the `AgentTask`, `AgentExternalEventHandler`, and the background `BridgeServer` listener thread. Pay close attention to how `AutoResetEvent` blocks the HTTP request thread until Revit's UI thread completes the task.
2. **[script.py](file:///d:/Construction/Projects/ai_revit_agent/extension/AI_Agent.extension/AI_Agent.tab/Panel.panel/StartBridge.pushbutton/script.py)**:
   * **Why**: See how the compiled C# assembly is loaded dynamically inside Revit's AppDomain, how the event handler is instantiated, and how the listener is started.
3. **[tools.py](file:///d:/Construction/Projects/ai_revit_agent/extension/AI_Agent.extension/AI_Agent.tab/Panel.panel/StartBridge.pushbutton/tools.py)**:
   * **Why**: Understand the Revit-side decorator-based `ToolRegistry`. Look at how the script router executes transactions and catches failures, and how basic tools (like `fetch_levels` or `create_grid`) interact with Revit's document objects.

### Checkpoints:
* Can you explain why the HTTP server accept loop (`ListenLoop`) must run on a background thread instead of the main Revit UI thread?
* What happens to an incoming web request if Revit is performing a modal command (e.g., waiting for user input) and cannot process the external event queue?

---

## Milestone 2: Backend Infrastructure & Tool Discovery (The Middleware)
Now that you understand how Revit receives requests, examine how the FastAPI backend establishes communication and dynamically indexes those tools.

### Study Order & Files:
1. **[revit_bridge.py](file:///d:/Construction/Projects/ai_revit_agent/backend/services/revit_bridge.py)**:
   * **Why**: Study the `RevitBridgeClient` class. Understand how HTTP connection pooling is initialized, how health checks are performed, and how responses are processed.
2. **[tool_registry.py](file:///d:/Construction/Projects/ai_revit_agent/backend/services/tool_registry.py)**:
   * **Why**: See how the backend caches the tool schemas discovered from Revit. Understand `_make_dispatcher` and how it wraps dynamic bridge execution endpoints in async closures to avoid late-binding scoping bugs.
3. **[config.py](file:///d:/Construction/Projects/ai_revit_agent/backend/config.py)**:
   * **Why**: Look at Pydantic settings loading and how the environment determines dev configurations, CORS parameters, and logging levels.

### Checkpoints:
* How does the backend differentiate between read-only tools (which run automatically) and modification tools?
* What is the purpose of the `schemas/tools.json` file snapshot created during startup?

---

## Milestone 3: Database & Persistence Layer (State Memory)
Before looking at the AI orchestrator, learn how conversation histories and settings configurations are saved on disk.

### Study Order & Files:
1. **[db.py](file:///d:/Construction/Projects/ai_revit_agent/backend/infra/db.py)**:
   * **Why**: Review the raw SQLite initialization. Read the four tables (`sessions`, `messages`, `provider_configs`, and `app_settings`). Understand the raw SQL design choice and how session updates are chained in single queries.

### Checkpoints:
* Why does the project avoid using SQLAlchemy or SQLModel ORMs?
* What details are stored under the `messages` table for `role = "tool"`?

---

## Milestone 4: Core AI Reasoning & Adapters (The Brain)
Examine how the AI orchestrator structures reasoning turns, streams thoughts, and invokes tools.

### Study Order & Files:
1. **[agent_loop.py](file:///d:/Construction/Projects/ai_revit_agent/backend/core/agent_loop.py)**:
   * **Why**: Read the multi-turn agentic execution logic inside `AgentOrchestrator.run`. Observe how the orchestrator is decoupled from web frameworks and handles the tool execution callback. Pay attention to how it filters out trailing `[object Object]` junk from the stream.
2. **[base.py](file:///d:/Construction/Projects/ai_revit_agent/backend/providers/base.py)**:
   * **Why**: Study the global `SYSTEM_PROMPT` rules which guide the AI to interact with Revit safely (explaining coordinate units, resolving levels, etc.).
3. **[gemini.py](file:///d:/Construction/Projects/ai_revit_agent/backend/providers/gemini.py)**:
   * **Why**: Learn how JSON tool schemas are dynamically mapped to Google Gemini's functional calling structure.

### Checkpoints:
* How does the `AgentOrchestrator` prevent runaway reasoning loops if the model keeps requesting tools?
* What is the purpose of the sliding buffer variable `_text_buffer` in the streaming tokenizer?

---

## Milestone 5: Routing & Event Streaming (The Transport)
Examine how the backend exposes endpoints, handles real-time streams, and cleans up connections.

### Study Order & Files:
1. **[streaming.py](file:///d:/Construction/Projects/ai_revit_agent/backend/services/streaming.py)**:
   * **Why**: Review how `SSEEventBuilder` serializes structured event dicts into standard Server-Sent Event lines (`data: {...}\n\n`).
2. **[chat.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/chat.py)**:
   * **Why**: Read the `POST /api/chat` route. Note the async event generator loop, the SSE response headers, and the fallback handler in the `finally:` block.
3. **[settings.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/settings.py)**:
   * **Why**: Review how the backend polls the status of the Revit bridge and re-registers tools dynamically when Revit comes back online.
4. **[main.py](file:///d:/Construction/Projects/ai_revit_agent/backend/main.py)**:
   * **Why**: Look at the startup lifespan block to see how components from all milestones are woven together.

### Checkpoints:
* If a user closes the browser tab while the agent is waiting for a tool execution to complete, what guarantees that the database records do not get corrupted?
* How does dynamic tool reloading work when Revit is booted after the backend is already running?

---

## Milestone 6: React Frontend & Global State (The Presentation)
Finally, study the frontend components that consume the SSE events and render the chat application.

### Study Order & Files:
1. **[client.ts](file:///d:/Construction/Projects/ai_revit_agent/frontend/src/api/client.ts)**:
   * **Why**: Learn how `openSSEStream` reads chunked bytes asynchronously from the HTTP body and yields structured event lines.
2. **[chatStore.ts](file:///d:/Construction/Projects/ai_revit_agent/frontend/src/store/chatStore.ts)**:
   * **Why**: Understand how Zustand state manages streaming events, updating tokens, thoughts, and cards on the fly.
3. **[ChatWindow.tsx](file:///d:/Construction/Projects/ai_revit_agent/frontend/src/components/ChatWindow.tsx)** & **[MessageBubble.tsx](file:///d:/Construction/Projects/ai_revit_agent/frontend/src/components/MessageBubble.tsx)**:
   * **Why**: Review how chat bubbles and tool execution cards (`ToolCallCard.tsx`) are rendered.

### Checkpoints:
* How does the frontend handle SSE connections aborted by the user clicking the "Stop" button?
* How does Zustand keep the sidebar session lists in sync when a new chat turn starts?

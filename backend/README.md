# ##############################################################
# AI-REVIT AGENT BACKEND: COMPREHENSIVE DOCUMENTATION
# ##############################################################

Welcome to the AI-Revit Agent Backend documentation. This file is written specifically for beginners to explain the architecture, data flow, database layer, and core logic of this system.

---

## 1. WHAT IS THIS PROJECT?

Autodesk Revit is the industry-standard software used by architects and structural engineers to design buildings (often called **Building Information Modeling** or **BIM**). Usually, design tasks (like drawing grids, placing levels, or aligning columns) are done manually, clicking buttons one by one.

This project introduces an **AI Agent** that can execute Revit design tasks automatically in response to natural language commands (e.g., *"Create a grid line named B from (0,0) to (100,0)"*).

### The Role of the Backend:
The backend acts as the **mediator** (middleman) between three major parts of the system:
1. **The Frontend (React Webpage)**: The user interface where users view the chat window, type instructions, configure API keys, and trigger actions.
2. **The AI Model (Google Gemini)**: The "brain" that reads user prompts, decides which tool to call, and generates conversational text replies.
3. **The Revit C# Bridge (Autodesk Revit)**: A lightweight HTTP server running inside the actual Revit process on the user's computer, executing geometric modifications on Revit documents.

---

## 2. HIGH-LEVEL ARCHITECTURE (THE THREE-LAYER DESIGN)

To keep the codebase easy to maintain, we organize the backend into a **Clean Architecture** with three decoupled layers. The rule is that dependencies flow **one way only**: 

`Presentation/API Layer` ──> `Core Domain Layer` ──> `Infrastructure Layer`

```
┌─────────────────────────────────────────────────────────────┐
│              1. PRESENTATION/API LAYER                      │
│  - backend/api/chat.py      - backend/api/sessions.py       │
│  - backend/api/settings.py  - backend/api/providers.py      │
│  Exposes HTTP endpoints and translates data to SSE streams.  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼ Calls (JSON/Dictionaries)
┌─────────────────────────────────────────────────────────────┐
│                 2. CORE DOMAIN LAYER                        │
│  - backend/core/agent_loop.py                               │
│  Runs the AI agentic reasoning loop. Completely independent │
│  of SQL databases, HTTP headers, or network protocols.      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼ Calls (JSON/Dictionaries)
┌─────────────────────────────────────────────────────────────┐
│                 3. INFRASTRUCTURE LAYER                     │
│  - backend/infra/db.py           (Direct SQL SQLite client) │
│  - backend/infra/revit_bridge.py (Revit communication client)│
│  Interacts with external hardware, files, databases, APIs.  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. LAYER-BY-LAYER CODE WALKTHROUGH

Here is an in-depth breakdown of the purpose and internal logic of every file in the backend.

### ### A. INFRASTRUCTURE LAYER (`backend/infra/`)

This layer deals with the outside world: databases and external network calls.

#### 1. [db.py](file:///d:/Construction/Projects/ai_revit_agent/backend/infra/db.py) (The Database Client)
Instead of using complex ORM (Object-Relational Mapping) libraries like SQLAlchemy, this file uses **raw SQL queries** wrapped in an asynchronous SQLite client using the `aiosqlite` package.
* **Why raw SQL?** It removes hundreds of lines of configuration boilerplate, completely avoids database lazy-loading bugs, and allows returning clean Python dictionaries (using `db.row_factory = aiosqlite.Row` and `dict(row)`) which naturally fit our agnostic boundary rule.
* **Key functions**:
  - `initialize()`: Boots up the SQLite database and creates four tables (`sessions`, `messages`, `provider_configs`, and `app_settings`) if they don't already exist.
  - `list_sessions()`: Lists all chat sessions, showing the most recently updated ones first.
  - `save_message()`: Stores a message (user prompt, AI response, or tool result) in the database and automatically updates the parent session's `updated_at` timestamp.
  - `save_provider_config()`: Saves API keys and selected model IDs. Ensures that when you set one provider to active, all other configurations are automatically deactivated.

#### 2. [revit_bridge.py](file:///d:/Construction/Projects/ai_revit_agent/backend/services/revit_bridge.py) (The Bridge Client)
This script is an HTTP client that talks to the C# server running inside Revit on port `8080`.
* **Key functions**:
  - `discover_tools()`: Sends a `GET` request to `http://127.0.0.1:8080/tools/` to fetch schemas of all available Revit tool functions (such as `create_grid` or `fetch_levels`).
  - `execute_tool()`: Sends a `POST` request to `http://127.0.0.1:8080/execute/` with a JSON payload telling Revit exactly which tool to run and with what arguments. If Revit is closed or the bridge fails, it raises an error that is returned to the user, ensuring the frontend's offline banner activates.

---

### ### B. CORE DOMAIN LAYER (`backend/core/`)

This is the brain of the backend. It has no idea that FastAPI or SQLite exists; it works strictly with raw inputs and outputs.

#### 1. [agent_loop.py](file:///d:/Construction/Projects/ai_revit_agent/backend/core/agent_loop.py) (The Orchestrator)
This file implements the **multi-turn AI reasoning loop**. It takes a history of messages and tool schemas, passes them to Gemini, and iterates.
* **What is a Multi-Turn Loop?** 
  When the user says: *"Align this level and then create a grid"*, the AI cannot do both at once. It must:
  1. Call `fetch_levels` tool.
  2. Wait for the levels data.
  3. Look at the output coordinates.
  4. Call `create_grid` tool.
  5. Wait for grid creation to complete.
  6. Return a friendly text response to the user.
* **Callback dependency**:
  Because the Core layer is decoupled, it doesn't call the database or Revit directly. Instead, it accepts an `execute_tool_fn` callback as a parameter. When it needs to execute a tool, it fires `await execute_tool_fn(tool_name, args)`.
* **JS Artifact Filtering**:
  Sometimes, web requests produce trailing `[object Object]` artifacts in JSON text fields. The loop implements a sliding buffer (`_text_buffer`) to filter these strings out before yielding text to the API.

---

### ### C. PRESENTATION/API LAYER (`backend/api/`)

This layer parses incoming HTTP requests, calls the core domain, and streams responses to the browser.

#### 1. [chat.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/chat.py) (Chat Controller)
Handles conversation endpoints.
* **SSE (Server-Sent Events)**:
  Instead of waiting for the AI to complete its entire reply (which takes a long time), this route returns a `StreamingResponse` using Server-Sent Events (SSE). It streams text chunks (deltas), status thoughts, and tool executions to the client character-by-character.
* **Disconnect/Cancellation Handlers**:
  If the user hits the **Stop** button, the browser aborts the request. FastAPI immediately raises a cancellation exception inside the generator. The route's `finally:` block catches this, stops Gemini's task, and commits all generated text and tool executions to SQLite so that no history is lost.

#### 2. [sessions.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/sessions.py) (Session Controller)
Exposes simple CRUD routes for chat sessions. It queries `Database` and returns serialized Pydantic responses.

#### 3. [settings.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/settings.py) & [providers.py](file:///d:/Construction/Projects/ai_revit_agent/backend/api/providers.py)
Manage app preference state (e.g. sidebars or UI configurations) and AI configurations. If Revit is offline, the status polling route `/api/revit/status` returns `{"connected": false, "tool_count": 0}`, notifying the frontend to render the offline warnings.

---

## 4. LIFECYCLE OF A CHAT REQUEST (STEP-BY-STEP)

Let's look at exactly what happens behind the scenes when a user types:
**"Create a grid named Grid-C from X=0 to X=100"** and clicks **Send**:

```
[User Interface]
       │  1. Sends POST /api/chat {"message": "Create grid...", "session_id": "123"}
       ▼
[chat.py (FastAPI Routing)]
       │  2. Calls db.get_session("123") and db.get_session_messages("123")
       ▼
[db.py (SQLite DB Layer)] 
       │  3. Reads SQLite database files, returns raw dictionary history
       ▼
[chat.py (FastAPI Routing)]
       │  4. Saves the user's message using db.save_message(...)
       │  5. Configures and instantiates the Gemini provider
       │  6. Starts the run_agent_loop(history, tool_schemas, execute_tool_callback)
       ▼
[agent_loop.py (Core Domain)]
       │  7. Passes message history to Gemini API
       │  8. Gemini returns a tool call: "create_grid" with start/end coordinates
       │  9. Yields {"type": "tool_call_pending"} event to API
       │ 10. Calls the callback execute_tool_callback("create_grid", args)
       ▼
[chat.py (FastAPI Routing)]
       │ 11. Resolves the tool name using registry.get_dispatcher("create_grid")
       │ 12. Invokes execute_tool("create_grid", args)
       ▼
[revit_bridge.py (Revit client)]
       │ 13. Sends POST http://127.0.0.1:8080/execute/ with grid parameters
       ▼
[Revit C# BridgeServer]
       │ 14. Queues task, runs on Revit main thread, writes grid, returns {"status": "success"}
       ▼
[agent_loop.py (Core Domain)]
       │ 15. Receives tool result and appends to prompt context
       │ 16. Asks Gemini for final text description ("I have created Grid-C successfully")
       │ 17. Yields {"type": "text_delta"} character chunks
       ▼
[chat.py (FastAPI Routing)]
       │ 18. Serializes all events to SSE (Server-Sent Events) and sends to browser
       │ 19. Generator ends; the finally: block saves the assistant's response to SQLite
```

---

## 5. DATABASE SCHEMA DESIGN

SQLite is self-contained in `data/agent.db`. Below are the four tables:

### 1. `sessions` (Chat rooms)
- `id` (TEXT, Primary Key): UUID identifying the chat.
- `name` (TEXT): Title shown in the sidebar (e.g. "Drafting Grids").
- `created_at` (TEXT): ISO 8601 creation timestamp.
- `updated_at` (TEXT): Last message timestamp (used to sort list).

### 2. `messages` (Conversation history)
- `id` (TEXT, Primary Key): Unique UUID.
- `session_id` (TEXT): Foreign key referencing `sessions.id` (cascades on delete).
- `role` (TEXT): `"user"` (human), `"assistant"` (AI), or `"tool"` (Revit response).
- `content` (TEXT): The message text or JSON-serialized tool output.
- `tool_calls` (TEXT, Optional): JSON list of tool invocations generated by the AI.
- `agent_thoughts` (TEXT, Optional): JSON list of synthetic status thoughts.
- `tool_name` (TEXT, Optional): The name of the tool (for `tool` role messages).
- `tool_call_id` (TEXT, Optional): Matches the ID of the tool call in the assistant message.
- `approved` (INTEGER, Optional): `1` for approved tool execution, `0` for rejected.
- `created_at` (TEXT): ISO 8601 timestamp.

### 3. `provider_configs` (API configurations)
- `id` (TEXT, Primary Key): UUID.
- `provider` (TEXT, Unique): Unique provider name (e.g., `"gemini"`).
- `api_key` (TEXT, Optional): The user's API key.
- `active_model` (TEXT, Optional): Selected model version (e.g. `"gemini-2.5-flash"`).
- `active` (INTEGER): `1` if this is the active provider, `0` otherwise.
- `updated_at` (TEXT): ISO 8601 update timestamp.

### 4. `app_settings` (UI preferences)
- `key` (TEXT, Primary Key): Setting name (e.g., `"theme"`).
- `value` (TEXT): Setting value string.
- `updated_at` (TEXT): ISO 8601 update timestamp.

---

## 6. CODING CONVENTIONS FOR FUTURE WORK

When updating this backend, always follow these rules to maintain code quality:
1. **Never import ORM frameworks**: Write clean, basic SQLite syntax inside [db.py](file:///d:/Construction/Projects/ai_revit_agent/backend/infra/db.py).
2. **Strict Layer Boundary Isolation**:
   - Do not import `Database` or use `FastAPI` structures inside `agent_loop.py`.
   - If the agent needs details from a new table, query it in `chat.py` first and pass the data inside a basic Python dictionary.
3. **OOP for Structural Entities**: Define structural components as classes (like `Database` or `AIProvider` subclasses) to maintain standard modular patterns.
4. **Use Asynchronous database connections**: Always write database functions with `async/await` utilizing `aiosqlite` so requests never block the main loop.

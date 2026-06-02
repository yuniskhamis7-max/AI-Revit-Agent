# System Context: Revit AI Agent

## Core Architecture
- **Local Python Daemon**: Runs standard Python 3.11+, handles Gemini API logic. Modular package structure (`bridge/`, `agent/`).
- **Revit-Side Bridge**: Runs inside Revit 2025 via pyRevit. Launches an asynchronous HTTP server on a background thread.
- **IPC Protocol**: Commands are passed via JSON over POST requests to `http://127.0.0.1:8080/execute`.

## Threading & Safe Execution
- Revit API execution is strictly single-threaded.
- The background HTTP thread enqueues tasks into a thread-safe `ConcurrentQueue<AgentTask>`.
- The background thread then raises an `ExternalEvent` which signals Revit's main thread to execute the tasks during its next idle cycle.
- The HTTP worker thread blocks using `AutoResetEvent` until the Revit UI thread completes execution and returns the result.

## Smart Context Fetching
- The daemon does NOT bulk-fetch project context at startup.
- Instead, the AI agent calls granular `fetch_*` tools during the conversation to gather only the data it needs.
- Available fetch tools: `fetch_project_info`, `fetch_levels`, `fetch_grids`, `fetch_families`, `fetch_sheets`.
- This reduces unnecessary Revit API calls and improves performance.

## Module Organization (Daemon)
```
daemon/
├── orchestrator.py      # Entry point: tool discovery + interactive loop
├── config.py            # API keys, bridge URLs, model config
├── bridge/
│   └── client.py        # Bridge HTTP communication + tool discovery
├── agent/
│   └── loop.py          # Gemini chat loop + system prompt
└── tests/
    ├── test_orchestrator.py    # Unit tests
    └── test_bridge_connection.py  # Connection diagnostics
```
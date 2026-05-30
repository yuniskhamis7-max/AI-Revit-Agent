# System Context: Revit AI Agent

## Core Architecture
- **Local Python Daemon**: Runs standard Python 3.11+, handles Gemini API logic. (Bypasses Revit API).
- **Revit-Side Bridge**: Runs inside Revit 2025 via pyRevit. Launches an asynchronous HTTP server on a background thread.
- **IPC Protocol**: Commands are passed via JSON over POST requests to `http://127.0.0.1:8080/execute`.

## Threading & Safe Execution
- Revit API execution is strictly single-threaded.
- The background HTTP thread enqueues tasks into a thread-safe `ConcurrentQueue<AgentTask>`.
- The background thread then raises an `ExternalEvent` which signals Revit's main thread to execute the tasks during its next idle cycle.
- The HTTP worker thread blocks using `AutoResetEvent` until the Revit UI thread completes execution and returns the result.
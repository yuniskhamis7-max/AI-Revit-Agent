# AI Revit Agent

AI Revit Agent is a minimal deterministic foundation for a scalable AI-assisted
Revit automation system built with Python, pyRevit, and clean architecture
principles.

This project validates the architecture, pyRevit button integration, import
flow, runtime structure, logging setup, deterministic BIM execution, and
human-approved payload execution flow. It intentionally does not include AI
features, advanced abstractions, databases, asynchronous execution, or broad
business automation logic.

## Architecture

- `extension/` contains the pyRevit extension structure that Revit loads.
- `extension/AIRevit.extension/AI.tab/Dev.panel/Test.pushbutton/script.py` is
  the pyRevit button entrypoint. It only makes the project root importable and
  calls the runtime executor.
- `app/` owns startup, bootstrap, configuration, and logging setup.
- `runtime/` owns orchestration, execution flow, workflow sequencing, and
  runtime context. It must not contain direct Revit API code.
- `revit/` owns direct Revit and pyRevit API interactions only, including
  transactions, levels, grids, document access, and UI dialogs.
- `tools/` contains pure helper utilities, payload loading, and JSON parsing.
- `schemas/` contains minimal structured placeholders for future AI-generated
  data.
- `state/` contains future runtime and session tracking placeholders.
- `tests/`, `data/`, and `docs/` are intentionally empty project folders.
- `logs/runtime`, `logs/errors`, and `logs/debug` are reserved logging folders.

## Current Runtime Flow

1. Revit loads the pyRevit extension from `extension/AIRevit.extension`.
2. The `AI` tab displays the `Dev` panel.
3. The `Test` button runs `script.py`.
4. `script.py` imports `runtime.executor.run()` and calls it.
5. `runtime.executor.run()` initializes logging through `app.main.bootstrap()`.
6. The user selects, previews, and optionally edits a JSON payload file.
7. The runtime validates the payload before execution approval.
8. The dispatcher executes approved payload actions sequentially.
9. Structured results are shown after execution.

Runtime logs are written to `logs/runtime/ai_revit_agent.log`.

## Register the Extension with pyRevit

From a terminal, register the extension folder with pyRevit:

```powershell
pyrevit extensions paths add "d:\Construction\Projects\ai_revit_agent\extension"
```

This registers the local folder that contains `AIRevit.extension`.

## Reload pyRevit

After registering or changing the extension, reload pyRevit:

```powershell
pyrevit reload
```

You can also reload from inside Revit using the pyRevit ribbon reload button.

## Open in VS Code

Open the project root folder directly:

```powershell
code "d:\Construction\Projects\ai_revit_agent"
```

Do not open only the `extension` folder. Opening the project root keeps imports,
logs, tests, and future modules visible in one workspace.

## Test Inside Revit

1. Start or restart Revit after registering the extension.
2. Confirm the `AI` tab is visible.
3. Open the `Dev` panel.
4. Click the `Test` button.
5. Select the sample payload file.
6. Review the payload preview.
7. Optionally edit the payload JSON.
8. Approve execution.
9. Confirm one test level and one test grid are created.
10. Confirm structured results are displayed.
11. Confirm `logs/runtime/ai_revit_agent.log` is created after clicking the button.

## Payload Files

Payload JSON files live in `data/payloads/`.

The included sample file is:

```text
data/payloads/sample_level_grid.json
```

Each action follows this standard shape:

```python
{
    "action": "create_level",
    "data": {
        "name": "AI Payload Level",
        "elevation": 15.0,
    },
}
```

## Test Payload Execution

Single payload execution can be tested from a pyRevit script context by calling
`runtime.workflow.execute_payload(document, payload)` with:

```python
{
    "action": "create_level",
    "data": {
        "name": "Payload Test Level",
        "elevation": 20.0,
    },
}
```

Multi-action execution can be tested with
`runtime.workflow.execute_payloads(document, payloads)` using:

```python
[
    {
        "action": "create_level",
        "data": {
            "name": "Payload Multi Level",
            "elevation": 30.0,
        },
    },
    {
        "action": "create_grid",
        "data": {
            "name": "Payload Multi Grid",
            "start": [0.0, 10.0, 0.0],
            "end": [30.0, 10.0, 0.0],
        },
    },
]
```

Validation failures can be tested by omitting a required field, using an
unsupported action, using non-number elevations, or passing grid points that are
not three-number lists.

Duplicate detection can be tested by running the same valid payload twice. The
second run should return a structured failure without creating another element.

Logging output is written to `logs/runtime/ai_revit_agent.log` and records
received payloads, validation failures, execution success, and execution errors.

Structured execution results use this shape:

```python
{
    "success": True,
    "message": "Payload execution completed. Succeeded: 2. Failed: 0.",
    "results": [
        {
            "success": True,
            "action": "create_level",
            "message": "Created level: Payload Multi Level",
            "error": None,
            "element_ids": [12345],
        }
    ],
}
```

## Test Runtime Console

Payload loading: click the `Test` button and select
`sample_level_grid.json` from `data/payloads/`.

Payload editing: choose to edit the payload, change a name or elevation, and
continue. The edited JSON is parsed and validated before execution.

Validation failures: remove a required field, use invalid JSON, set an elevation
to text, use an unsupported action, or make grid points invalid. The workflow
should stop before execution and show validation results.

Approval flow: use a valid payload, skip or complete editing, then approve the
execution prompt. The level and grid should be created.

Cancellation flow: cancel file selection, cancel editing, or cancel final
approval. No Revit elements should be created.

Multi-action execution: use the sample payload list. Actions are processed
sequentially and each action receives its own structured result.

Result visualization: after execution, the result dialog shows success, action,
message, error, and created element IDs for each payload action.

Payload persistence: add more `.json` files to `data/payloads/`; they will be
available from the payload selection dialog.

Logging behavior: check `logs/runtime/ai_revit_agent.log` for loaded files,
edited payloads, validation failures, approval decisions, execution results, and
execution errors.

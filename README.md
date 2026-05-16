# AI Revit Agent

AI Revit Agent is a minimal deterministic foundation for a scalable AI-assisted
Revit automation system built with Python, pyRevit, and clean architecture
principles.

This project validates the architecture, pyRevit button integration, import
flow, runtime structure, logging setup, deterministic BIM execution, and
human-approved payload execution flow. It also includes a controlled
natural-language interpreter for simple BIM instructions. It intentionally does
not include external AI APIs, advanced abstractions, databases, asynchronous
execution, or broad business automation logic.

## Architecture

- `extension/` contains the pyRevit extension structure that Revit loads.
- `extension/AIRevit.extension/AI Revit.tab/Execution.panel/Run Instruction.pushbutton/script.py`
  is the pyRevit button entrypoint. It only makes the project root importable
  and calls the runtime executor.
- `app/` owns startup, bootstrap, configuration, and logging setup.
- `runtime/` owns orchestration, execution flow, workflow sequencing, and
  runtime context. It must not contain direct Revit API code.
- `interpreter/` converts controlled user language into structured payloads. It
  must not contain Revit API logic or execution logic.
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
2. The `AI Revit` tab displays the `Execution` panel.
3. The `Run Instruction` button runs `script.py`.
4. `script.py` imports `runtime.executor.run()` and calls it.
5. `runtime.executor.run()` initializes logging through `app.main.bootstrap()`.
6. The instruction editor opens immediately.
7. Natural-language instructions are parsed into structured payloads.
8. The user previews and optionally edits generated payload JSON.
9. The runtime validates the payload before execution approval.
10. The dispatcher executes approved payload actions sequentially.
11. Structured results are shown after execution.

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
2. Confirm the `AI Revit` tab is visible.
3. Open the `Execution` panel.
4. Click the `Run Instruction` button.
5. Enter a supported controlled instruction.
6. Review the generated payload preview.
7. Optionally edit the payload JSON.
8. Approve execution.
9. Confirm the requested level or grid elements are created.
10. Confirm structured results are displayed.
11. Confirm `logs/runtime/ai_revit_agent.log` is created after clicking the button.

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

Instruction entry: click the `Run Instruction` button and enter a supported
controlled instruction.

Payload editing: choose to edit the generated payload, change a name or
elevation, and continue. The edited JSON is parsed and validated before
execution.

Validation failures: remove a required field, use invalid JSON, set an elevation
to text, use an unsupported action, or make grid points invalid. The workflow
should stop before execution and show validation results.

Approval flow: use a valid payload, skip or complete editing, then approve the
execution prompt. The level and grid should be created.

Cancellation flow: cancel instruction entry, payload editing, or final approval.
No Revit elements should be created.

Multi-action execution: use an instruction such as
`Create 3 levels spaced 4000 mm apart` or `Create grids A, B, and C`. Actions
are processed sequentially and each action receives its own structured result.

Result visualization: after execution, the result dialog shows success, action,
message, error, and created element IDs for each payload action.

Logging behavior: check `logs/runtime/ai_revit_agent.log` for user
instructions, generated payloads, edited payloads, validation failures, approval
decisions, execution results, and execution errors.

## Test Instructions

Valid natural-language instructions:

```text
Create 3 levels spaced 4000 mm apart
Create grids A, B, and C
Create Level 1 at elevation 0
Create grid A from 0,0 to 0,10000
```

Invalid instructions: use unsupported verbs, missing values, negative spacing,
or text that does not match the controlled grammar. The interpreter should show
a structured interpretation failure and stop before payload validation.

Ambiguous instructions: enter `Create grid A` or `Create levels`. These should
fail because they do not provide enough deterministic execution data.

Payload generation: after entering a valid instruction, review the generated
payload preview. Numeric instruction values are converted to Revit internal feet;
instructions default to millimeters unless `m` or `ft` is provided.

Payload editing: choose to edit the generated payload JSON before validation.
Invalid JSON or invalid payload values should stop before execution.

Execution approval: approve the final prompt to execute validated payloads.

Execution cancellation: cancel instruction entry, payload editing, or final
approval. No Revit elements should be created.

Structured execution results: after execution, inspect the result dialog for
success, action, message, error, and created element IDs.

Interpreter logging: check `logs/runtime/ai_revit_agent.log` for user
instructions, interpretation results, generated payloads, interpretation
failures, validation failures, approval decisions, and execution results.

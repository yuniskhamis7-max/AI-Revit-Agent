# AI Revit Agent

AI Revit Agent is a minimal first-phase scaffold for a scalable AI-assisted
Revit automation system built with Python, pyRevit, and clean architecture
principles.

This phase validates the architecture, pyRevit button integration, import flow,
runtime structure, logging setup, and development workflow. It intentionally
does not include AI features, advanced abstractions, databases, asynchronous
execution, or business automation logic.

## Architecture

- `extension/` contains the pyRevit extension structure that Revit loads.
- `extension/AIRevit.extension/AI.tab/Dev.panel/Test.pushbutton/script.py` is
  the pyRevit button entrypoint. It only makes the project root importable and
  calls the runtime executor.
- `app/` owns startup, bootstrap, configuration, and logging setup.
- `runtime/` owns orchestration, execution flow, workflow placeholders, and
  runtime context. It must not contain direct Revit API code.
- `revit/` owns direct Revit and pyRevit API interactions only.
- `tools/` contains pure helper utilities and placeholders.
- `schemas/` contains minimal structured placeholders for future AI-generated
  data.
- `state/` contains future runtime and session tracking placeholders.
- `tests/`, `data/`, and `docs/` are intentionally empty phase-one folders.
- `logs/runtime`, `logs/errors`, and `logs/debug` are reserved logging folders.

## Current Runtime Flow

1. Revit loads the pyRevit extension from `extension/AIRevit.extension`.
2. The `AI` tab displays the `Dev` panel.
3. The `Test` button runs `script.py`.
4. `script.py` imports `runtime.executor.run()` and calls it.
5. `runtime.executor.run()` calls `app.main.bootstrap()`.
6. `app.main.bootstrap()` initializes logging and calls `revit.ui.show_loaded_message()`.
7. `revit.ui.show_loaded_message()` displays `AI Revit Agent Loaded`.

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
5. Confirm the popup says `AI Revit Agent Loaded`.
6. Confirm `logs/runtime/ai_revit_agent.log` is created after clicking the button.

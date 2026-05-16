# AI Revit Agent

AI Revit Agent is a lightweight pyRevit drafting environment. The AI converts a
human instruction into structured JSON payload data; deterministic Revit tools
validate and execute only the selected BIM category.

The AI never generates Revit API code, Python code, transactions, or execution
steps. It only returns data shaped like:

```json
{
    "levels": [],
    "grids": [],
    "columns": []
}
```

## Layers

- `extension/` contains the pyRevit ribbon buttons.
- `ai/` converts instructions into JSON payloads using Gemini.
- `revit/` contains deterministic Revit operations and pyRevit UI only.
- `run.py` saves `payload.json`, validates it, logs runs, and executes button flow.
- `payload.json` is the current generated payload.

No agents, memory systems, databases, async workers, or orchestration framework
are included.

## Ribbon

The `AI Revit` tab contains four panels:

- `Payload` -> `Generate Payload`
- `Levels` -> `Create Levels`
- `Grids` -> `Create Grids`
- `Columns` -> `Create Columns`

`Generate Payload` is the only button that asks for a natural-language
instruction. It asks the AI to generate a full payload that can contain levels,
grids, and columns, then saves it to `payload.json`.

The category buttons do not ask for instructions. They load the current payload,
preview only their category section, validate only that category, and execute
only that category after approval.

## AI Setup

The AI layer uses Gemini 2.5 Flash. A project key is configured in
`ai/parser.py`, and you can override it with an environment variable:

```powershell
$env:GEMINI_API_KEY = "your_api_key"
```

Optional model override:

```powershell
$env:GEMINI_MODEL = "gemini-2.5-flash"
```

The current AI-generated payload is saved at `payload.json`.
Runtime logs are written to `logs/runtime/ai_revit_agent.log`.

## How To Test

AI instruction parsing: click `Generate Payload` and enter a clear instruction
such as `Create two levels named Level 1 and Level 2 spaced 4000 mm apart`.

Payload generation: inspect `payload.json` after the AI call. It
should contain only `levels`, `grids`, and `columns` arrays.

Payload preview: after generation, the dialog should show the full generated
payload. Category execution buttons should then preview only their own section.

Category-based execution: enter a mixed instruction containing levels, grids,
and columns. Click one category button and confirm unrelated categories do not
execute.

Levels-only execution: click `Create Levels` with generated level payloads.
Only levels should be created.

Grids-only execution: click `Create Grids` with generated grid payloads. Only
grids should be created.

Columns-only execution: click `Create Columns` with generated column payloads.
Referenced levels and the family/type must exist in the model.

Validation failures: ask for invalid data or manually edit
`payload.json` during development, then run the relevant button.
Missing required fields or invalid points/elevations should stop before
execution.

Duplicate detection: run the same level or grid request twice. The second run
should fail with a duplicate-name validation message.

Logging behavior: inspect `logs/runtime/ai_revit_agent.log` for user
instructions, AI payloads, validation failures, approvals, and execution
results.

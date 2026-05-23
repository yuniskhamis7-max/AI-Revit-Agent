# AI Revit Agent

AI Revit Agent is a pyRevit extension for driving early Autodesk Revit model
setup from validated AI intent. The active workflow opens a conversational
dashboard, sends the current model context and user instructions to Gemini,
validates the proposed delta, compiles it into Revit-ready data, and applies the
result to levels and grids in a controlled transaction.

The project is intentionally conservative at the Revit boundary. AI output is
treated as proposed structured data first; only compiled and validated data is
allowed to reach the Revit API.

## Current Features

- pyRevit ribbon extension under the `AI Revit` tab.
- `Build From AI` command that launches the conversational structural setup
  workflow.
- Gemini-backed intent service with model selection and cached local
  configuration.
- WinForms dashboard for prompt input, AI response review, KPI display, proposed
  create/update/delete actions, and final execution approval.
- Typed internal models for levels, grids, points, settings, and compiled project
  data.
- Direct unit compiler that converts AI deltas into Revit internal feet and
  derives grid extents from the proposed footprint.
- Revit structural manager that caches existing levels and grids, tracks managed
  elements through Comments metadata, applies updates, recreates grids when
  extents change, and executes approved deletions.
- Documentation for setup, architecture, payload/intent schema, and full project
  source inventory.

## Repository Layout

```text
extension/
  AIRevit.extension/                 pyRevit extension, tab, panels, and buttons
    AI Revit.tab/
      Generation.panel/
        BuildFromAI.pushbutton/      active pyRevit entrypoint
      Levels.panel/                  reserved button surface
      Grids.panel/                   reserved button surface
      Columns.panel/                 reserved button surface
airevitlib/
  core/
    config.py                        local API/model configuration
    models.py                        typed internal data objects
    orchestrator.py                  UI, AI, compiler, and Revit transaction flow
  services/
    ai.py                            Gemini client and intent request handling
    compiler.py                      AI delta to Revit-ready model compiler
    auditor.py                       validation/auditing helpers
  revit/
    coordinates.py                   coordinate transforms
    elements.py                      Revit level/grid creation, update, delete logic
  ui/
    forms.py                         WinForms dashboard and message dialogs
docs/
  ARCHITECTURE.md                    runtime structure and design notes
  INTENT_SCHEMA.md                   expected AI intent response shape
  PAYLOAD_SCHEMA.md                  sample payload contract
  PYREVIT_SETUP.md                   pyRevit installation and troubleshooting
payload.json                         minimal sample structured input
PROJECT_DOCUMENTATION.txt            generated project inventory and source dump
CONTRIBUTING.md                      contribution guidelines
```

## Runtime Flow

```text
Build From AI pyRevit button
  -> StructuralBIMAgentOrchestrator
  -> BIMConversationalDashboard
  -> GeminiClient
  -> proposed_delta JSON
  -> DirectUnitCompiler
  -> CompiledProjectData
  -> StructuralManager
  -> Revit DB.Transaction
```

The orchestrator captures existing Revit levels and grids once, keeps
conversation memory during the dashboard session, and applies only the final
validated payload after the user confirms execution.

## Ribbon Buttons

The extension is organized around these pyRevit panels:

- `Generation` -> `Build From AI`
- `Levels` -> `Create Levels`
- `Grids` -> `Create Grids`
- `Columns` -> `Create Columns`

Current status:

- `Build From AI` is the active command.
- `Create Levels`, `Create Grids`, and `Create Columns` are reserved entrypoints
  for future focused workflows.

## Setup

See [docs/PYREVIT_SETUP.md](docs/PYREVIT_SETUP.md) for pyRevit setup and
troubleshooting.

Short version:

1. Clone this repository.
2. Add `extension/AIRevit.extension` as a pyRevit extension path.
3. Reload pyRevit.
4. Open Revit and use `AI Revit` -> `Generation` -> `Build From AI`.

The command can read a Gemini API key from `GEMINI_API_KEY` or from the local
git-ignored `airevit_config.json` file created by the dashboard.

## Data Contracts

The current AI workflow expects an intent-style response with a `proposed_delta`
for levels and grids. The compiler currently standardizes incoming AI numeric
values as meters before converting to Revit internal feet.

See [docs/INTENT_SCHEMA.md](docs/INTENT_SCHEMA.md) for the AI response shape and
[docs/PAYLOAD_SCHEMA.md](docs/PAYLOAD_SCHEMA.md) for the sample payload shape.

## Safety

These commands can create, update, pin, unpin, rename, recreate, and delete Revit
elements after user approval. Develop and test on a copied model until the
workflow matches your office standards. Managed levels and grids are tracked
with `AI_ID:LVL:` and `AI_ID:GRD:` markers in the Comments parameter.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Intent Schema](docs/INTENT_SCHEMA.md)
- [Payload Schema](docs/PAYLOAD_SCHEMA.md)
- [pyRevit Setup](docs/PYREVIT_SETUP.md)
- [Full Project Documentation](PROJECT_DOCUMENTATION.txt)
- [Contributing](CONTRIBUTING.md)

## Roadmap

- Bring `docs/ARCHITECTURE.md` fully in sync with the current `airevitlib/`
  pipeline.
- Add stricter schema validation before transaction execution.
- Implement focused workflows for the reserved levels, grids, and columns
  buttons.
- Add automated tests for pure-Python compiling, validation, and intent parsing.
- Add richer dry-run previews before committing Revit transactions.

## License

No license has been selected yet. Add a `LICENSE` file before publishing if you
want others to use, modify, or redistribute the project.

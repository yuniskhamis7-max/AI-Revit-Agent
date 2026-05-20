# AI Revit Agent

AI Revit Agent is a pyRevit extension for generating early structural setup
elements in Autodesk Revit from structured project data. The current
implementation focuses on a deterministic pipeline for levels and grids:
payload JSON is parsed into typed data objects, then Revit manager classes create
or update model elements inside a single transaction.

The project is intentionally conservative at the Revit boundary. AI-assisted
input should become validated JSON first; only validated data should reach the
Revit API.

## Current Features

- pyRevit ribbon extension under the `AI Revit` tab.
- `Build From AI` command that parses a sample JSON payload and generates levels
  and grids.
- Typed payload DTOs for project, level, grid, and point data.
- `PayloadManager` for parsing raw JSON into typed project data.
- `LevelManager` for creating or updating levels, pinning them, and creating
  floor plan views when requested.
- `GridManager` for creating safe grid lines, preserving existing grids by
  default, and pinning generated grids.
- Placeholder column button for a future payload-driven column workflow.
- Documentation for setup, architecture, and payload structure.

## Repository Layout

```text
extension/
  AIRevit.extension/                 pyRevit extension, tab, panels, and buttons
lib/
  dtos.py                            Typed payload data objects
  payload_manager.py                 JSON parsing and payload mapping
  revit_managers/
    level_manager.py                 Revit level creation/update behavior
    grid_manager.py                  Revit grid creation/update behavior
docs/
  ARCHITECTURE.md                    Runtime structure and design notes
  PAYLOAD_SCHEMA.md                  JSON payload contract
  PYREVIT_SETUP.md                   pyRevit installation and troubleshooting
payload.json                         Example payload data
CONTRIBUTING.md                      Contribution guidelines
```

## Ribbon Buttons

The extension is organized around these pyRevit panels:

- `Generation` -> `Build From AI`
- `Levels` -> `Create Levels`
- `Grids` -> `Create Grids`
- `Columns` -> `Create Columns`

Current status:

- `Build From AI` is the active end-to-end command for level and grid generation.
- `Create Levels` and `Create Grids` are currently inactive button stubs.
- `Create Columns` is a placeholder entrypoint for future column placement.

## Setup

See [docs/PYREVIT_SETUP.md](docs/PYREVIT_SETUP.md) for pyRevit setup and
troubleshooting.

Short version:

1. Clone this repository.
2. Add `extension/AIRevit.extension` as a pyRevit extension path.
3. Reload pyRevit.
4. Open Revit and use the `AI Revit` tab.

## Payloads

The payload layer currently supports `levels` and `grids`. The sample
`payload.json` also includes columns as a future target, but column entries are
not executed yet.

See [docs/PAYLOAD_SCHEMA.md](docs/PAYLOAD_SCHEMA.md) for the expected JSON
shape.

## Safety

These commands can create, update, pin, and rename Revit elements. Develop and
test on a copied model until the workflow is stable for your office standards.
Existing grids are preserved by the current grid manager unless a force-recreate
path is explicitly used in code.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Payload Schema](docs/PAYLOAD_SCHEMA.md)
- [pyRevit Setup](docs/PYREVIT_SETUP.md)
- [Contributing](CONTRIBUTING.md)

## Roadmap

- Replace the embedded sample payload in `Build From AI` with a real payload
  source.
- Add stricter payload validation and user-facing validation messages.
- Implement payload-driven column placement.
- Add dry-run previews before committing Revit transactions.
- Add automated tests for pure-Python payload parsing and validation.

## License

No license has been selected yet. Add a `LICENSE` file before publishing if you
want others to use, modify, or redistribute the project.

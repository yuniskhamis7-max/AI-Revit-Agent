# AI Revit Agent

AI Revit Agent is a work-in-progress pyRevit extension for automating early BIM
setup tasks in Autodesk Revit. The current code focuses on deterministic Revit
API helpers for levels and grids, with placeholder ribbon entrypoints for future
payload generation and column execution.

The long-term direction is simple: use structured data as the boundary between
AI-assisted input and Revit execution. Generated data can be reviewed and
validated before any model changes are made.

## Features

- pyRevit ribbon extension under the `AI Revit` tab.
- Reusable `Level` helper for creating, offsetting, pinning, renaming, deleting,
  and creating plan views for Revit levels.
- Reusable `Grid` helper for creating anchor grids, offset grids, copying grids
  from linked models, and pinning grids.
- Example `payload.json` format for future levels, grids, and columns execution.
- Documentation for setup, architecture, and payload structure.

## Repository Layout

```text
extension/
  AIRevit.extension/       pyRevit extension, tab, panels, and button scripts
lib/
  Levels.py                Revit level helper
  Grids.py                 Revit grid helper
docs/
  ARCHITECTURE.md          Runtime structure and design notes
  PAYLOAD_SCHEMA.md        Planned JSON payload contract
  PYREVIT_SETUP.md         pyRevit installation and troubleshooting
payload.json               Example payload data
```

## Ribbon Buttons

The `AI Revit` tab contains four panels:

- `Payload` -> `Generate Payload`
- `Levels` -> `Create Levels`
- `Grids` -> `Create Grids`
- `Columns` -> `Create Columns`

Current status:

- `Create Levels` runs a sample level creation workflow.
- `Create Grids` runs demonstration grid workflows for manual testing.
- `Generate Payload` and `Create Columns` are placeholder entrypoints.

## Setup

See [docs/PYREVIT_SETUP.md](docs/PYREVIT_SETUP.md) for pyRevit setup and
troubleshooting.

Short version:

1. Clone this repository.
2. Add `extension/AIRevit.extension` as a pyRevit extension path.
3. Reload pyRevit.
4. Open Revit and use the `AI Revit` tab.

## Safety

These commands can create, rename, pin, and optionally delete Revit elements.
Develop and test on a copied model until the workflow is stable for your office
standards.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Payload Schema](docs/PAYLOAD_SCHEMA.md)
- [pyRevit Setup](docs/PYREVIT_SETUP.md)
- [Contributing](CONTRIBUTING.md)

## Project Name Ideas

The best GitHub-ready name is **Revit Structure Starter** because the current
code creates foundational structural setup elements: levels, grids, and future
columns.

Other good options:

- **Revit Layout Agent**
- **BIM Scaffold**
- **Revit Setup Assistant**
- **GridLevel AI**
- **Revit Datum Builder**

## Roadmap

- Connect `Generate Payload` to a real parser or AI provider.
- Validate `payload.json` before model execution.
- Implement payload-driven level, grid, and column creation buttons.
- Add dry-run previews before committing Revit transactions.
- Add automated validation tests for pure-Python payload logic once that layer
  exists outside Revit.

## License

No license has been selected yet. Add a `LICENSE` file before publishing if you
want others to use, modify, or redistribute the project.

# pyRevit Setup

## Requirements

- Autodesk Revit with pyRevit installed.
- Python code executed through pyRevit's configured Python engine.
- A test Revit model or a copy of a production model.

## Install the Extension

1. Clone this repository.
2. In pyRevit, add the repository's `extension/AIRevit.extension` folder as an
   extension path.
3. Reload pyRevit.
4. Open Revit and look for the `AI Revit` tab.

## Development Workflow

1. Edit reusable behavior in `lib/`.
2. Edit button-level pyRevit behavior under `extension/AIRevit.extension/`.
3. Reload pyRevit after changes.
4. Run commands in a disposable Revit model.
5. Review messages in the pyRevit output panel.

The active generation workflow is the `Build From AI` button. It currently uses
an embedded sample payload in its button script; `payload.json` documents the
external payload shape that future work can load from disk or another provider.

## Troubleshooting

- If imports from `lib` fail, confirm the button script is adding the shared
  library path to `sys.path`.
- If Revit API imports fail, confirm the script is running inside Revit through
  pyRevit.
- If levels are not created, check whether a level with the same name already
  exists; matching levels are updated by name.
- If grids are not created, check whether a grid with the same name already
  exists; matching grids are preserved by name.
- If a grid is skipped, confirm its start and end points are valid and far
  enough apart for Revit to create a line.

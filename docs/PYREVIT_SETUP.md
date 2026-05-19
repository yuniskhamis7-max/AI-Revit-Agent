# pyRevit Setup

## Requirements

- Autodesk Revit with pyRevit installed.
- Python code executed through pyRevit/IronPython or pyRevit's configured Python
  engine.
- A test Revit model or a copy of a production model.

## Install the Extension

1. Clone this repository.
2. In pyRevit, add the repository's `extension/AIRevit.extension` folder as an
   extension path.
3. Reload pyRevit.
4. Open Revit and look for the `AI Revit` tab.

## Development Workflow

1. Edit files in `lib/` for reusable Revit behavior.
2. Edit button-level `script.py` files under `extension/AIRevit.extension/` for
   pyRevit command behavior.
3. Reload pyRevit after changes.
4. Run commands in a disposable Revit model and watch the pyRevit output panel
   for messages.

## Troubleshooting

- If imports from `lib` fail, confirm the repository root is being added to
  `sys.path` by the button script.
- If Revit API imports fail, confirm the script is running inside Revit through
  pyRevit.
- If elements are not created, check whether an element with the same name
  already exists.
- If copied grids do not appear, confirm the linked model is loaded and contains
  simple grid curves.

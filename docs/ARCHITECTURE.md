# Architecture

This repository is a pyRevit extension with a small shared Python library.

## Runtime Layers

- `extension/AIRevit.extension/` defines the pyRevit ribbon tab, panels, and
  button entrypoints.
- `lib/` contains reusable Revit API wrappers for levels and grids.
- `payload.json` is an example payload shape for future payload-driven tools.

The current implementation is intentionally deterministic. Ribbon scripts call
known Python functions, and the reusable library performs Revit API operations
inside explicit transactions.

## pyRevit Entry Points

Each `script.py` file is launched by pyRevit from its button folder. The scripts
add the repository root to `sys.path` so they can import modules from `lib/`.

Current button status:

- `Create Levels`: creates a sample level system, optional floor plans, and can
  prompt before cleaning old levels.
- `Create Grids`: runs demonstration grid scenarios for manual testing.
- `Generate Payload`: placeholder entrypoint for future AI or payload creation.
- `Create Columns`: placeholder entrypoint for future column execution.

## Revit Transactions

Revit document mutations must run inside a `DB.Transaction`. The shared helpers
keep transaction names specific so failures are easier to diagnose in Revit.

## Units

Revit stores model distances internally in feet. Public helper methods accept
millimeters (`mm`), meters (`m`), or internal feet depending on the `unit`
argument.

## Safety Notes

Run these scripts on a copy of a Revit model while developing. Several commands
create, pin, rename, or optionally delete model elements.

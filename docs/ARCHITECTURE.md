# Architecture

This repository is a pyRevit extension with a small shared Python library. The
design goal is to keep AI or external input outside the Revit API until it has
been converted into predictable, typed project data.

## Runtime Layers

- `extension/AIRevit.extension/` defines the pyRevit ribbon tab, panels, and
  button entrypoints.
- `lib/dtos.py` defines the typed data objects used by the payload layer.
- `lib/payload_manager.py` parses raw JSON into `ProjectData`.
- `lib/revit_managers/` contains Revit API manager classes for model changes.
- `payload.json` is an example payload and future external input target.

The current implementation is deterministic. The active command uses known JSON
input, maps it into DTOs, and then applies it to Revit through explicit manager
methods.

## pyRevit Entry Points

Each `script.py` file is launched by pyRevit from its button folder. Button
scripts add the shared library path to `sys.path` so they can import modules from
`lib/`.

Current button status:

- `Build From AI`: active command that parses a sample payload and creates or
  updates levels and grids.
- `Create Levels`: inactive stub.
- `Create Grids`: inactive stub.
- `Create Columns`: placeholder for future column payload execution.

## Data Flow

```text
JSON payload
  -> PayloadManager
  -> ProjectData / LevelData / GridData / Point2D
  -> LevelManager / GridManager
  -> Revit DB.Transaction
  -> Revit document
```

The payload manager is responsible for turning raw JSON into typed data. Revit
managers are responsible for document lookups, conflict handling, and Revit API
calls.

## Revit Transactions

Document mutations must run inside a `DB.Transaction`. The active generation
workflow groups level and grid creation in one transaction so the operation can
roll back if a Revit API error occurs midway.

## Levels

`LevelManager` builds a cache of existing levels by name. When processing a
payload level, it updates the elevation of an existing level with the same name
or creates a new level when none exists. It can also pin levels and create floor
plan views.

## Grids

`GridManager` builds a cache of existing grids by name. When processing a payload
grid, it preserves existing grids and only updates their pinned state. New grids
are created from `Point2D` start and end coordinates after a minimum length
check.

## Units

Revit stores model distances internally in feet. Current payload numeric values
are passed directly to the Revit API, so payload coordinates and elevations
should be provided in Revit internal feet unless a future unit conversion layer
is added.

## Safety Notes

Run these scripts on a copy of a Revit model while developing. Commands can
create, update, pin, rename, or delete model elements depending on which manager
methods are used.

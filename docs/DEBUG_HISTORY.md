# Debug History

This project was restructured from a flat, mixed-responsibility pyRevit script
into a decoupled, stateful, coordinate-safe conversational BIM pipeline. The key
debugging findings and fixes are summarized below.

## Architecture and Runtime

- **Stale pyRevit bytecode:** pyRevit kept custom modules cached in Revit's
  persistent AppDomain, so edits to files such as `forms.py` and
  `orchestrator.py` were ignored until Revit restarted. The entrypoint now
  performs sequential hot reloads, clearing custom modules and reloading them
  from disk each time the button runs.
- **.NET namespace collisions:** Flat imports such as
  `from System.Windows.Forms import Label` collided with other CLR types, most
  notably `System.Reflection.Emit.Label`. UI code now uses fully qualified
  module aliases such as `WinForms.Label()` and `WinForms.TextBox()`.
- **Strict PythonNet typing:** CPython/.NET constructor calls failed when Python
  values relied on implicit conversion, such as integer font sizes or raw enum
  integers. UI and interop code now passes explicit .NET-friendly types, for
  example `9.0` and `Drawing.FontStyle.Bold`.

## Conversation and Model State

- **Lost conversation context:** Earlier AI calls were stateless, so follow-up
  replies lost prior intent and current Revit model context. The orchestrator now
  keeps a static model-state cache plus chronological chat history and sends the
  complete conversation context on each turn.
- **Coordinate shifts from project offsets:** Project Base Point offsets shifted
  grids away from levels, splitting the visible model. `CoordinateUtility` now
  applies consistent `X`, `Y`, and `Z` translations to both grids and levels.

## Geometry and Compilation

- **Single-axis grid failures:** The compiler expected both grid axes to exist,
  so one-axis requests could collapse into empty output. The compiler now
  supports single-axis layouts and derives a default fallback length when the
  opposite axis is not specified.
- **Grid versus bay fencepost errors:** AI prompts sometimes treated requested
  grid count as bay count, producing one extra grid. System instructions now
  enforce that `N` grids create exactly `N` elements, while `N` bays create
  `N + 1` elements.
- **Null KPI formatting crashes:** Incomplete layouts could return `null`
  footprint metrics, and formatting `None` as a float crashed the dashboard
  thread. Dashboard metric rendering now uses null-safe defaults such as `0.0`.

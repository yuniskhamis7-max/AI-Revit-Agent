# Payload Schema

`payload.json` is the planned interchange format between natural-language
generation and deterministic Revit commands.

The current buttons do not fully execute this schema yet, but the file documents
the intended contract so future development has a stable target.

## Root Object

```json
{
  "levels": [],
  "grids": [],
  "columns": []
}
```

All three keys should be present. Use an empty array when a category has no
requested elements.

## Levels

```json
{
  "name": "Ground Floor",
  "elevation": 0.0
}
```

- `name`: Revit level name.
- `elevation`: Elevation in Revit internal feet unless a future executor adds a
  unit field.

## Grids

```json
{
  "name": "A",
  "start": [0.0, -16.4042],
  "end": [0.0, 49.2126]
}
```

- `name`: Revit grid name.
- `start`: XY start point in Revit internal feet.
- `end`: XY end point in Revit internal feet.

## Columns

```json
{
  "family": "Rectangular Concrete Column",
  "type": "400x400",
  "base_level": "Ground Floor",
  "top_level": "Roof",
  "location": [0.0, 0.0]
}
```

- `family`: Revit family name.
- `type`: Revit family type name.
- `base_level`: Existing base level name.
- `top_level`: Existing top level name.
- `location`: XY insertion point in Revit internal feet.

## Validation Goals

Before model execution, future payload-driven buttons should validate:

- Required root keys exist.
- Element names are non-empty strings.
- Numeric values are finite numbers.
- Points have exactly two numeric coordinates.
- Referenced levels, families, and types exist in the active Revit document.
- New level and grid names do not conflict with existing elements unless the
  command intentionally updates existing elements.

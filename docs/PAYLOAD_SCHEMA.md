# Payload Schema

`payload.json` is the intended interchange format between AI-assisted generation
and deterministic Revit commands.

The active payload parser currently supports `levels` and `grids`. The example
payload may include `columns`, but column execution is still planned work.

## Root Object

```json
{
  "levels": [],
  "grids": []
}
```

`levels` and `grids` are optional in the current parser and default to empty
lists when omitted. Keeping both keys present is recommended for readability and
future validation.

## Levels

```json
{
  "name": "L0 - Ground Floor",
  "elevation": 0.0,
  "is_pinned": true,
  "create_floor_plan": true
}
```

- `name`: Revit level name.
- `elevation`: Elevation in Revit internal feet.
- `is_pinned`: Optional. Defaults to `true`.
- `create_floor_plan`: Optional. Defaults to `true`.

## Grids

```json
{
  "name": "A",
  "start": {
    "x": -5.0,
    "y": 0.0
  },
  "end": {
    "x": 105.0,
    "y": 0.0
  },
  "is_pinned": true
}
```

- `name`: Revit grid name.
- `start`: XY start point in Revit internal feet.
- `end`: XY end point in Revit internal feet.
- `is_pinned`: Optional. Defaults to `true`.

Grid points must use object form with `x` and `y` fields. Array points such as
`[0.0, 10.0]` are not accepted by the current parser.

## Planned Columns

```json
{
  "family": "Rectangular Concrete Column",
  "type": "400x400",
  "base_level": "Ground Floor",
  "top_level": "Roof",
  "location": {
    "x": 0.0,
    "y": 0.0
  }
}
```

- `family`: Revit family name.
- `type`: Revit family type name.
- `base_level`: Existing base level name.
- `top_level`: Existing top level name.
- `location`: XY insertion point in Revit internal feet.

Column payloads are documented as a target contract, but they are not parsed or
executed by the current generation command.

## Validation Goals

Before model execution, payload-driven commands should validate:

- Required data categories exist or intentionally default to empty lists.
- Element names are non-empty strings.
- Numeric values are finite numbers.
- Points contain exactly `x` and `y` numeric coordinates.
- Grid start and end points are far enough apart for Revit to create a line.
- Referenced levels, families, and types exist in the active Revit document.
- New level and grid names do not conflict with existing elements unless the
  command intentionally updates existing elements.

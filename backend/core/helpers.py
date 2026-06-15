# -*- coding: utf-8 -*-
"""
Helper Functions for State Fetching, Summary Formatting, Context Injection,
and Programmatic Safety Duplicate Filtering.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def fetch_existing_state(
    execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    history: list[dict] | None = None,
) -> dict:
    """
    Fetch the current Revit model state (levels, grids, columns, column_types) selectively
    based on the categories mentioned in the user prompt history.

    Each fetch is independently caught — a failure in one does not abort
    the others. Returns a structured dict with both raw lists and fast
    lookup sets.
    """
    state: dict = {
        "levels":       [],
        "grids":        [],
        "columns":      [],
        "column_types": [],  # list of loaded column types
        "level_names":  set(),   # lowercase for case-insensitive match
        "grid_names":   set(),   # exact case as returned by Revit
        "fetched":      {"levels": False, "grids": False, "columns": False, "column_types": False}
    }

    # Analyze keywords in history to query only related categories
    fetch_levels = False
    fetch_grids = False
    fetch_columns = False
    fetch_column_types = False

    if history:
        user_texts = [
            m["content"].lower() for m in history
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        combined_text = " ".join(user_texts)
        
        has_column = any(w in combined_text for w in ("column", "pillar", "post", "structural"))
        has_grid = any(w in combined_text for w in ("grid", "axis", "gridline", "spacing", "wall", "partition", "floor", "slab", "ceiling", "roof"))
        has_level = any(w in combined_text for w in ("level", "elevation", "height", "storey", "datum", "room", "space", "area"))
        has_clear_all = any(w in combined_text for w in ("delete", "clear", "remove", "clean", "reset", "empty", "all elements"))

        if has_clear_all or has_column:
            fetch_levels = True
            fetch_grids = True
            fetch_columns = True
            fetch_column_types = True
        elif has_grid:
            fetch_levels = True
            fetch_grids = True
            fetch_columns = False
            fetch_column_types = False
        elif has_level:
            fetch_levels = True
            fetch_grids = False
            fetch_columns = False
            fetch_column_types = False
        else:
            # Fallback: fetch datums if ambiguous
            fetch_levels = True
            fetch_grids = True
            fetch_columns = False
            fetch_column_types = False
    else:
        # Fallback if no history is provided (fetch datums)
        fetch_levels = True
        fetch_grids = True
        fetch_columns = False
        fetch_column_types = False

    state["fetched"] = {
        "levels": fetch_levels,
        "grids": fetch_grids,
        "columns": fetch_columns,
        "column_types": fetch_column_types
    }

    if fetch_levels:
        try:
            res = await execute_tool_fn("fetch_levels", {})
            state["levels"] = res.get("data", {}).get("levels", [])
            state["level_names"] = {
                lvl["name"].strip().lower() for lvl in state["levels"]
            }
        except Exception as exc:
            logger.warning("fetch_levels failed: %s", exc)

    if fetch_grids:
        try:
            res = await execute_tool_fn("fetch_grids", {})
            state["grids"] = res.get("data", {}).get("grids", [])
            state["grid_names"] = {g["name"].strip() for g in state["grids"]}
        except Exception as exc:
            logger.warning("fetch_grids failed: %s", exc)

    if fetch_columns:
        try:
            res = await execute_tool_fn("fetch_structural_columns", {})
            state["columns"] = res.get("data", {}).get("columns", [])
        except Exception as exc:
            logger.warning("fetch_structural_columns failed (non-fatal): %s", exc)

    if fetch_column_types:
        try:
            res = await execute_tool_fn("fetch_structural_column_types", {})
            state["column_types"] = res.get("data", {}).get("column_types", [])
        except Exception as exc:
            logger.warning("fetch_structural_column_types failed (non-fatal): %s", exc)

    return state


def format_state_summary(state: dict) -> str:
    """
    Format the existing model state dict into a compact, human-readable
    summary string suitable for injecting into agent prompts.
    """
    lines: list[str] = []
    fetched = state.get("fetched", {"levels": True, "grids": True, "columns": True, "column_types": False})

    if fetched.get("levels"):
        if state["levels"]:
            lvl_str = ", ".join(
                f"'{l['name']}' ({l.get('elevation', l.get('elevation_ft', 0.0))} ft, ID: '{l['level_id']}')"
                for l in state["levels"]
            )
            lines.append(f"Levels ({len(state['levels'])}): {lvl_str}")
        else:
            lines.append("Levels: None")
    else:
        lines.append("Levels: (Not fetched for this task)")

    if fetched.get("grids"):
        if state["grids"]:
            grid_str = ", ".join(f"'{g['name']}' (ID: '{g['grid_id']}')" for g in state["grids"])
            lines.append(f"Grids ({len(state['grids'])}): {grid_str}")
        else:
            lines.append("Grids: None")
    else:
        lines.append("Grids: (Not fetched for this task)")

    if fetched.get("columns"):
        col_count = len(state["columns"])
        lines.append(
            f"Structural Columns: {col_count} existing"
            if col_count else "Structural Columns: None"
        )
    else:
        lines.append("Structural Columns: (Not fetched for this task)")

    if fetched.get("column_types"):
        if state.get("column_types"):
            types_str = ", ".join(
                f"'{t['name']}' (Family: '{t['family_name']}', ID: '{t['column_type_id']}')"
                for t in state["column_types"]
            )
            lines.append(f"Structural Column Types ({len(state['column_types'])}): {types_str}")
        else:
            lines.append("Structural Column Types: None")
    else:
        lines.append("Structural Column Types: (Not fetched for this task)")

    return "\n".join(lines)


def inject_state_context(
    history: list[dict],
    existing_state: dict,
) -> list[dict]:
    """
    Append a system-role message containing the current model state to
    the conversation history. This gives every downstream agent awareness
    of what already exists in Revit.
    """
    context_parts: list[str] = []
    fetched = existing_state.get("fetched", {"levels": True, "grids": True, "columns": True, "column_types": False})

    if fetched.get("levels") and existing_state["levels"]:
        lvl_str = ", ".join(
            f"'{l['name']}' ({l.get('elevation', l.get('elevation_ft', 0.0))} ft, ID: '{l['level_id']}')"
            for l in existing_state["levels"]
        )
        context_parts.append(f"Existing levels: {lvl_str}")

    if fetched.get("grids") and existing_state["grids"]:
        grid_lines = []
        for g in existing_state["grids"]:
            start = g.get("start_coords") or {}
            end = g.get("end_coords") or {}
            sx, sy = start.get("x", 0.0), start.get("y", 0.0)
            ex, ey = end.get("x", 0.0), end.get("y", 0.0)
            grid_lines.append(f"Grid '{g['name']}' (ID: '{g['grid_id']}', from ({sx}, {sy}) to ({ex}, {ey}) ft)")
        grid_str = ", ".join(grid_lines)
        context_parts.append(f"Existing grids: {grid_str}")

    if fetched.get("columns") and existing_state["columns"]:
        col_lines = []
        for c in existing_state["columns"][:150]:
            loc = c.get("location", {})
            x = loc.get("x", 0.0)
            y = loc.get("y", 0.0)
            base_lvl = c.get("base_level_name") or "Unknown"
            top_lvl = c.get("top_level_name") or "Unknown"
            col_lines.append(f"Type '{c['column_type']}' (ID: '{c['column_id']}') at ({x}, {y}) ft (Base: '{base_lvl}', Top: '{top_lvl}')")
        col_str = "; ".join(col_lines)
        if len(existing_state["columns"]) > 150:
            col_str += f" (and {len(existing_state['columns']) - 150} more columns)"
        context_parts.append(f"Existing columns: {col_str}")

    if fetched.get("column_types") and existing_state.get("column_types"):
        type_lines = [
            f"Type '{t['name']}' (Family: '{t['family_name']}', ID: '{t['column_type_id']}')"
            for t in existing_state["column_types"]
        ]
        type_str = ", ".join(type_lines)
        context_parts.append(f"Existing structural column types: {type_str}")

    if not context_parts:
        return list(history)

    note = (
        "Current Revit project state:\n"
        + "\n".join(context_parts)
        + "\n\n"
        "Reuse existing elements where appropriate. "
        "Do not propose names that conflict with existing ones."
    )

    return list(history) + [{"role": "system", "content": note}]


def filter_duplicate_calls(
    batch_data: dict,
    existing_state: dict,
) -> tuple[dict, str]:
    """
    Programmatic safety net — deterministically filters two classes of
    problematic calls before they reach the atomic execute_batch transaction:

    1. **Duplicate creates** — removes create_level / create_grid / duplicate_structural_column_type calls for
       elements that already exist in Revit (prevents name-conflict aborts).

    2. **Phantom deletes** — removes delete_level / delete_grid /
       delete_structural_column / delete_structural_column_type calls whose
       target ID is NOT present in the fetched model state (prevents "element not found"
       aborts caused by stale or LLM-hallucinated IDs).

    This runs regardless of what the LLM agents produced, ensuring a bad
    LLM day cannot cause a Revit transaction abort.

    Returns:
        (filtered_batch_data, human_readable_report_string)
    """
    filtered:              list[dict] = []
    skipped_levels:        list[str]  = []
    skipped_grids:         list[str]  = []
    skipped_column_types:  list[str]  = []
    conflicting_levels:    list[str]  = []
    phantom_deletes:       list[str]  = []

    existing_levels      = existing_state.get("levels", [])
    existing_level_names = existing_state.get("level_names", set())
    existing_grid_names  = existing_state.get("grid_names",  set())
    existing_column_types = existing_state.get("column_types", [])
    existing_column_type_names = {
        t["name"].strip().lower() for t in existing_column_types if "name" in t
    }

    # Build fast ID lookup sets from the fetched state.
    # These are used to validate delete calls before they reach the batch.
    existing_level_ids: set[str] = {
        l["level_id"] for l in existing_levels if "level_id" in l
    }
    existing_grid_ids: set[str] = {
        g["grid_id"] for g in existing_state.get("grids", []) if "grid_id" in g
    }
    existing_column_ids: set[str] = {
        c["column_id"] for c in existing_state.get("columns", []) if "column_id" in c
    }
    existing_column_type_ids: set[str] = {
        t["column_type_id"] for t in existing_column_types if "column_type_id" in t
    }

    # Map each delete tool to its ID field name and the known-ID set.
    # If the known-ID set is empty (category was not fetched), we pass the
    # call through unchanged — we can only guard what we have fetched.
    _delete_id_map: dict[str, tuple[str, set[str]]] = {
        "delete_level":                  ("level_id",  existing_level_ids),
        "delete_grid":                   ("grid_id",   existing_grid_ids),
        "delete_structural_column":      ("column_id", existing_column_ids),
        "delete_structural_column_type": ("column_type_id", existing_column_type_ids),
    }

    # ── Pre-scan: collect element IDs and names being deleted in this batch ───
    # When an element is being deleted AND re-created with the same name, the
    # duplicate-create guard must NOT skip the creation — the element will no
    # longer exist after the deletion within the same atomic transaction.
    batch_deleting_grid_ids: set[str] = set()
    batch_deleting_level_ids: set[str] = set()
    batch_deleting_column_type_ids: set[str] = set()
    batch_deleting_grid_names: set[str] = set()
    batch_deleting_level_names: set[str] = set()
    batch_deleting_column_type_names: set[str] = set()

    # Build ID→name lookup from existing state
    _grid_id_to_name: dict[str, str] = {
        g["grid_id"]: g["name"].strip()
        for g in existing_state.get("grids", []) if "grid_id" in g and "name" in g
    }
    _level_id_to_name: dict[str, str] = {
        l["level_id"]: l["name"].strip()
        for l in existing_levels if "level_id" in l and "name" in l
    }
    _column_type_id_to_name: dict[str, str] = {
        t["column_type_id"]: t["name"].strip()
        for t in existing_column_types if "column_type_id" in t and "name" in t
    }

    for call in batch_data.get("calls", []):
        tool = call.get("tool", "")
        inp = call.get("input", {})
        if tool == "delete_grid":
            gid = inp.get("grid_id", "").strip()
            if gid:
                batch_deleting_grid_ids.add(gid)
                name = _grid_id_to_name.get(gid)
                if name:
                    batch_deleting_grid_names.add(name)
        elif tool == "delete_level":
            lid = inp.get("level_id", "").strip()
            if lid:
                batch_deleting_level_ids.add(lid)
                name = _level_id_to_name.get(lid)
                if name:
                    batch_deleting_level_names.add(name.lower())
        elif tool == "delete_structural_column_type":
            ctid = inp.get("column_type_id", "").strip()
            if ctid:
                batch_deleting_column_type_ids.add(ctid)
                name = _column_type_id_to_name.get(ctid)
                if name:
                    batch_deleting_column_type_names.add(name.lower())

    for call in batch_data.get("calls", []):
        tool = call.get("tool", "")
        inp  = call.get("input", {})

        # ── Phantom-delete guard ──────────────────────────────────────────────
        if tool in _delete_id_map:
            id_field, known_ids = _delete_id_map[tool]
            element_id = inp.get(id_field, "").strip()
            # Only validate when we have fetched that category (non-empty set).
            if known_ids and element_id and element_id not in known_ids:
                phantom_deletes.append(
                    f"  ⚠️ Skipped '{tool}' — ID '{element_id}' not found in "
                    f"fetched model state (stale or hallucinated ID)."
                )
                logger.warning(
                    "filter_duplicate_calls: dropping phantom delete — "
                    "tool='%s' id='%s' not in known IDs.",
                    tool, element_id,
                )
                continue  # drop this call — it would abort the batch

        # ── Duplicate-create guard ────────────────────────────────────────────
        # Skip the guard when the element is being deleted in the same batch
        # (delete-then-recreate pattern).  The element will no longer exist
        # after the deletion within the atomic transaction.
        elif tool == "create_level":
            name  = inp.get("name", "").strip()
            lower = name.lower()

            if lower in existing_level_names and lower not in batch_deleting_level_names:
                existing_lvl = next(
                    (l for l in existing_levels
                     if l["name"].strip().lower() == lower), None
                )
                if existing_lvl:
                    ex_elev     = existing_lvl.get(
                        "elevation", existing_lvl.get("elevation_ft", 0.0)
                    )
                    target_elev = inp.get("elevation", 0.0)
                    if abs(ex_elev - target_elev) > 0.01:
                        conflicting_levels.append(
                            f"  ⚠️ Level '{name}' exists at {ex_elev} ft "
                            f"but plan says {target_elev} ft — skipping creation."
                        )
                    else:
                        skipped_levels.append(name)
                continue  # always skip — never create a duplicate level name

        elif tool == "create_grid":
            name = inp.get("name", "").strip()
            if name in existing_grid_names and name not in batch_deleting_grid_names:
                skipped_grids.append(name)
                continue  # skip — grid already exists

        elif tool == "duplicate_structural_column_type":
            new_name = inp.get("new_type_name", "").strip()
            lower = new_name.lower()
            if lower in existing_column_type_names and lower not in batch_deleting_column_type_names:
                skipped_column_types.append(new_name)
                continue  # skip — column type already exists

        filtered.append(call)

    batch_data["calls"] = filtered

    report_lines: list[str] = []
    if skipped_levels:
        report_lines.append(
            f"  Skipped existing level(s) — reusing: {', '.join(skipped_levels)}"
        )
    if skipped_grids:
        report_lines.append(
            f"  Skipped existing grid(s) — reusing: {', '.join(skipped_grids)}"
        )
    if skipped_column_types:
        report_lines.append(
            f"  Skipped duplicating existing column type(s) — reusing: {', '.join(skipped_column_types)}"
        )
    if conflicting_levels:
        report_lines.extend(conflicting_levels)
    if phantom_deletes:
        report_lines.extend(phantom_deletes)

    return batch_data, "\n".join(report_lines)


def inject_schemas_context(
    history: list[dict],
    tool_schemas: list[dict],
) -> list[dict]:
    """
    Format and inject available tool schemas as a system-role message.
    This gives the clarifier, designer, planner, parser, and validator
    complete structural details of the available APIs in Revit.
    """
    if not tool_schemas:
        return list(history)

    schema_summary = []
    for ts in tool_schemas:
        schema_summary.append({
            "name": ts["name"],
            "description": ts.get("description", ""),
            "parameters": ts.get("parameters", {})
        })

    note = (
        "AVAILABLE REVIT TOOLS AND SCHEMAS:\n"
        "Use this context to check parameters, design layout tables, "
        "formulate plans, translate JSON payloads, and validate properties.\n"
        f"```json\n{json.dumps(schema_summary, indent=2)}\n```"
    )
    return list(history) + [{"role": "system", "content": note}]


# ─────────────────────────────────────────────────────────────────────────────
# Post-Execution Real-State Fetcher
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_created_elements(
    execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    batch_data: dict,
    batch_result: dict,
) -> dict:
    """
    Fetch the actual Revit state for elements created (and deleted) in a batch.

    After execute_batch completes, the individual create_* responses only contain
    an element_id — no coordinates or level names.  This function bridges that gap
    by calling the relevant fetch_* tools and filtering down to just the elements
    that belong to the current batch (matched by element_id).

    The returned dict is structured for direct consumption by the reverse-state
    parser prompt, which converts it into a Result Design Manual with real values.

    Returns a dict with keys:
        grids            — list of grid objects (real coords) for created grids
        columns          — list of column objects (real location) for created columns
        deleted_grid_ids     — list of grid IDs that were successfully deleted
        deleted_column_ids   — list of column IDs that were successfully deleted
        failures             — list of failed tool-call entries from the batch
    """
    calls:   list[dict] = batch_data.get("calls", [])
    results: list[dict] = (
        batch_result.get("data", {}).get("results", [])
        if batch_result.get("status") == "success"
        else []
    )

    # ── Collect created element IDs by category ───────────────────────────────
    created_grid_ids:   set[str] = set()
    created_column_ids: set[str] = set()

    for res_item in results:
        tool = res_item.get("tool", "")
        eid  = res_item.get("result", {}).get("data", {}).get("element_id", "")
        if not eid:
            continue
        if tool == "create_grid":
            created_grid_ids.add(eid)
        elif tool == "create_structural_column":
            created_column_ids.add(eid)

    # ── Collect successfully deleted element IDs ──────────────────────────────
    deleted_grid_ids:   list[str] = []
    deleted_column_ids: list[str] = []

    for res_item in results:
        tool   = res_item.get("tool", "")
        status = res_item.get("result", {}).get("status", "")
        inp    = res_item.get("input", {})
        if status != "success":
            continue
        if tool == "delete_grid":
            gid = inp.get("grid_id", "")
            if gid:
                deleted_grid_ids.append(gid)
        elif tool == "delete_structural_column":
            cid = inp.get("column_id", "")
            if cid:
                deleted_column_ids.append(cid)

    # ── Collect failures ──────────────────────────────────────────────────────
    failures: list[dict] = []
    for res_item in results:
        if res_item.get("result", {}).get("status") == "error":
            failures.append({
                "tool":    res_item.get("tool", ""),
                "input":   res_item.get("input", {}),
                "message": res_item.get("result", {}).get("message", ""),
            })
    # Also capture top-level error if batch itself failed
    if batch_result.get("status") == "error":
        failures.append({
            "tool":    "execute_batch",
            "input":   {},
            "message": batch_result.get("message", "Batch failed"),
        })

    # ── Fetch actual Revit state for created elements ─────────────────────────
    actual_grids:   list[dict] = []
    actual_columns: list[dict] = []

    if created_grid_ids:
        try:
            res = await execute_tool_fn("fetch_grids", {})
            all_grids: list[dict] = res.get("data", {}).get("grids", [])
            # Filter to only the grids that were just created in this batch
            actual_grids = [
                g for g in all_grids
                if g.get("grid_id", "") in created_grid_ids
            ]
            logger.info(
                "fetch_created_elements: fetched %d grids, matched %d to batch creates.",
                len(all_grids), len(actual_grids),
            )
        except Exception as exc:
            logger.warning("fetch_created_elements: fetch_grids failed: %s", exc)
            failures.append({
                "tool":    "fetch_grids",
                "input":   {},
                "message": str(exc),
            })

    if created_column_ids:
        try:
            res = await execute_tool_fn("fetch_structural_columns", {})
            all_cols: list[dict] = res.get("data", {}).get("columns", [])
            # Filter to only columns created in this batch
            actual_columns = [
                c for c in all_cols
                if c.get("column_id", "") in created_column_ids
            ]
            logger.info(
                "fetch_created_elements: fetched %d columns, matched %d to batch creates.",
                len(all_cols), len(actual_columns),
            )
        except Exception as exc:
            logger.warning(
                "fetch_created_elements: fetch_structural_columns failed: %s", exc
            )
            failures.append({
                "tool":    "fetch_structural_columns",
                "input":   {},
                "message": str(exc),
            })

    return {
        "grids":               actual_grids,
        "columns":             actual_columns,
        "deleted_grid_ids":    deleted_grid_ids,
        "deleted_column_ids":  deleted_column_ids,
        "failures":            failures,
    }

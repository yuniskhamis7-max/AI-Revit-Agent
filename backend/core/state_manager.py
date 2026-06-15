# -*- coding: utf-8 -*-
"""
ModelStateManager — Schema-driven BIM state orchestration.

Replaces the scattered helper functions in helpers.py with a cohesive OOP class.
All category-level knowledge is derived at runtime from the tool schemas received
from the Revit bridge — no category names are hardcoded anywhere in this file.

Usage:
    manager = ModelStateManager(tool_schemas)
    state   = await manager.fetch_existing_state(execute_tool_fn, history)
    summary = manager.format_summary(state)
    history = manager.inject_context(history, state)
    batch, report = manager.filter_duplicates(batch_data, state)
    created = await manager.fetch_created_elements(execute_tool_fn, batch_data, result)

Adding a new BIM element category (e.g. beams, walls, MEP) requires ZERO changes
to this file. The developer adds a new tool file on the Revit side and annotates
the @registry.register() calls with the appropriate metadata fields.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Words that indicate a destructive / global operation requiring full state fetch
_GLOBAL_OPERATION_KEYWORDS = frozenset({
    "delete", "clear", "remove", "clean", "reset", "empty", "all elements"
})


class ModelStateManager:
    """
    Derives all BIM model state logic from the tool schemas at runtime.

    One instance is created per orchestration context (sharing tool_schemas),
    allowing the expensive category map to be built once and reused across
    all five pipeline operations.
    """

    def __init__(self, tool_schemas: list[dict]) -> None:
        self.tool_schemas = tool_schemas
        # Built once, reused by all methods — avoids repeated schema iteration.
        self._category_map: dict[str, dict] = self._build_category_map()

    # ─────────────────────────────────────────────────────────────────────────
    # Category map — built once from schemas
    # ─────────────────────────────────────────────────────────────────────────

    def _build_category_map(self) -> dict[str, dict]:
        """
        Derive the full category configuration purely from tool schema metadata.

        Iterates the schemas received from the Revit bridge and groups them by
        their 'category' field.  Each entry accumulates fetch/create/delete/
        duplicate tool names, plus id_field, name_field, keywords, etc.

        Returns:
            dict keyed by category name (e.g. "levels", "grids", "columns").
        """
        categories: dict[str, dict] = {}

        for schema in self.tool_schemas:
            cat = schema.get("category")
            if not cat:
                continue  # meta-tools like execute_batch have no category

            if cat not in categories:
                categories[cat] = {
                    "fetch_tool":    None,
                    "data_key":      cat,       # sensible default
                    "id_field":      None,
                    "name_field":    None,
                    "keywords":      [],
                    "name_case":     "lower",
                    "always_fetch":  False,
                    "create_tool":   None,
                    "delete_tool":   None,
                    "duplicate_tool": None,
                }

            name = schema.get("name", "")
            cfg  = categories[cat]

            if name.startswith("fetch_"):
                cfg["fetch_tool"]   = name
                cfg["data_key"]     = schema.get("data_key", cat)
                cfg["always_fetch"] = bool(schema.get("always_fetch", False))
                if schema.get("keywords"):
                    # Extend to allow multiple fetch tools to contribute keywords
                    cfg["keywords"] = list(schema["keywords"])

            elif name.startswith("delete_"):
                cfg["delete_tool"] = name
                if schema.get("id_field"):
                    cfg["id_field"] = schema["id_field"]

            elif name.startswith("create_"):
                cfg["create_tool"] = name
                if schema.get("name_field"):
                    cfg["name_field"] = schema["name_field"]
                if schema.get("name_case"):
                    cfg["name_case"] = schema["name_case"]

            elif name.startswith("duplicate_"):
                cfg["duplicate_tool"] = name
                # duplicate tools define the new-name field (e.g. new_type_name)
                if schema.get("name_field"):
                    cfg["name_field"] = schema["name_field"]
                if schema.get("name_case"):
                    cfg["name_case"] = schema["name_case"]

            # Any tool in the category may declare id_field (e.g. create_* that
            # returns an element_id so the backend can track created elements).
            if schema.get("id_field") and not cfg["id_field"]:
                cfg["id_field"] = schema["id_field"]

        return categories

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def fetch_existing_state(
        self,
        execute_tool_fn: Callable[[str, dict[str, Any]], Any],
        categories_to_fetch: list[str] | None = None,
    ) -> dict:
        """
        Fetch the current Revit model state for all relevant categories.

        Selectively calls only the fetch_* tools corresponding to the categories
        specified in categories_to_fetch. If categories_to_fetch is None, all categories
        with a registered fetch tool will be fetched.
        """
        state: dict = {"fetched": {}}

        for cat_name, cfg in self._category_map.items():
            fetch_tool = cfg["fetch_tool"]
            data_key   = cfg["data_key"]

            if categories_to_fetch is None:
                should_fetch = bool(fetch_tool)
            else:
                should_fetch = cat_name in categories_to_fetch

            state[cat_name]              = []
            state["fetched"][cat_name]   = should_fetch

            if should_fetch and fetch_tool:
                try:
                    res = await execute_tool_fn(fetch_tool, {})
                    state[cat_name] = res.get("data", {}).get(data_key, [])
                except Exception as exc:
                    logger.warning("%s failed: %s", fetch_tool, exc)

            # Build fast lookup sets from fetched data
            self._build_lookup_sets(state, cat_name, cfg)

        return state

    def format_summary(self, state: dict) -> str:
        """
        Format the model state dict into a compact, human-readable summary
        suitable for injecting into agent system prompts.

        Uses field-detection to show rich data (elevation for levels,
        coordinates for grids, location for columns) without hardcoding
        per-category formatting logic.
        """
        lines: list[str] = []
        fetched = state.get("fetched", {})

        for cat_name, cfg in self._category_map.items():
            if not cfg["fetch_tool"]:
                continue

            label = cat_name.replace("_", " ").title()

            if not fetched.get(cat_name):
                lines.append(f"{label}: (Not fetched for this task)")
                continue

            items: list[dict] = state.get(cat_name, [])
            if not items:
                lines.append(f"{label}: None")
                continue

            item_strs = [
                self._format_item(item, cfg["id_field"])
                for item in items
            ]
            lines.append(f"{label} ({len(items)}): {', '.join(item_strs)}")

        return "\n".join(lines)

    def inject_context(
        self,
        history: list[dict],
        existing_state: dict,
    ) -> list[dict]:
        """
        Append a system-role message containing the current model state to the
        conversation history, giving every downstream agent awareness of what
        already exists in Revit.
        """
        context_parts: list[str] = []
        fetched = existing_state.get("fetched", {})

        for cat_name, cfg in self._category_map.items():
            if not cfg["fetch_tool"] or not fetched.get(cat_name):
                continue

            items: list[dict] = existing_state.get(cat_name, [])
            if not items:
                continue

            # Limit very large collections to avoid bloating the context window
            display_items = items[:150]
            parts = [self._format_item(item, cfg["id_field"]) for item in display_items]
            if len(items) > 150:
                parts.append(f"(and {len(items) - 150} more)")

            context_parts.append(
                f"Existing {cat_name.replace('_', ' ')}: {', '.join(parts)}"
            )

        if not context_parts:
            return list(history)

        note = (
            "Current Revit project state:\n"
            + "\n".join(context_parts)
            + "\n\nReuse existing elements where appropriate. "
            "Do not propose names that conflict with existing ones."
        )
        return list(history) + [{"role": "system", "content": note}]

    def filter_duplicates(
        self,
        batch_data: dict,
        existing_state: dict,
    ) -> tuple[dict, str]:
        """
        Programmatic safety net — deterministically filters two classes of
        problematic calls before they reach the atomic execute_batch transaction:

        1. Phantom deletes — delete_* calls whose target ID is NOT present in
           the fetched model state (stale or hallucinated IDs).
        2. Duplicate creates — create_* / duplicate_* calls for elements whose
           name already exists in Revit (prevents name-conflict transaction aborts).

        The delete-then-recreate pattern is explicitly handled: if an element is
        being deleted in the same batch, its name is removed from the duplicate
        guard so the subsequent create_* is allowed through.

        Returns:
            (filtered_batch_data, human_readable_report_string)
        """
        # ── Build delete-guard maps from category config ──────────────────────
        delete_id_map: dict[str, tuple[str, set]] = {}
        for cat_name, cfg in self._category_map.items():
            delete_tool = cfg["delete_tool"]
            id_field    = cfg["id_field"]
            if delete_tool and id_field:
                known_ids = existing_state.get(f"{cat_name}_ids", set())
                delete_id_map[delete_tool] = (id_field, known_ids)

        # ── Build id→name lookups for delete-then-recreate tracking ──────────
        id_to_name: dict[str, dict[str, str]] = {}  # cat_name -> {id: name}
        for cat_name, cfg in self._category_map.items():
            id_field   = cfg["id_field"]
            name_field = cfg["name_field"]
            name_case  = cfg["name_case"]
            items = existing_state.get(cat_name, [])
            if id_field and name_field and items:
                mapping = {}
                for item in items:
                    iid  = item.get(id_field, "").strip()
                    inam = item.get(name_field, "").strip()
                    if iid and inam:
                        mapping[iid] = inam.lower() if name_case == "lower" else inam
                id_to_name[cat_name] = mapping

        # ── Pre-scan: collect IDs/names being deleted in this batch ──────────
        batch_deleting_names: dict[str, set] = {}  # cat_name -> set of names
        batch_deleting_ids:   dict[str, set] = {}  # cat_name -> set of ids

        for call in batch_data.get("calls", []):
            tool = call.get("tool", "")
            inp  = call.get("input", {})
            for cat_name, cfg in self._category_map.items():
                if tool != cfg.get("delete_tool"):
                    continue
                id_field = cfg["id_field"]
                if not id_field:
                    continue
                eid = inp.get(id_field, "").strip()
                if eid:
                    batch_deleting_ids.setdefault(cat_name, set()).add(eid)
                    name = id_to_name.get(cat_name, {}).get(eid)
                    if name:
                        batch_deleting_names.setdefault(cat_name, set()).add(name)

        # ── Main filter loop ──────────────────────────────────────────────────
        filtered: list[dict] = []
        skipped: dict[str, list[str]] = {}
        phantom_deletes: list[str] = []

        for call in batch_data.get("calls", []):
            tool = call.get("tool", "")
            inp  = call.get("input", {})
            skip = False

            # ── Phantom-delete guard ──────────────────────────────────────────
            if tool in delete_id_map:
                id_field, known_ids = delete_id_map[tool]
                element_id = inp.get(id_field, "").strip()
                # Only validate when we've fetched that category (non-empty set)
                if known_ids and element_id and element_id not in known_ids:
                    phantom_deletes.append(
                        f"  ⚠️ Skipped '{tool}' — ID '{element_id}' not found in "
                        "fetched model state (stale or hallucinated ID)."
                    )
                    logger.warning(
                        "filter_duplicates: dropping phantom delete — "
                        "tool='%s' id='%s' not in known IDs.", tool, element_id,
                    )
                    skip = True

            else:
                # ── Duplicate-create / duplicate-duplicate guard ──────────────
                for cat_name, cfg in self._category_map.items():
                    if tool not in (cfg.get("create_tool"), cfg.get("duplicate_tool")):
                        continue  # not the right category — keep looking

                    # Found the matching category for this create/duplicate tool
                    name_field = cfg["name_field"]
                    if not name_field:
                        break  # category is position-based (no name uniqueness constraint)

                    name_case      = cfg["name_case"]
                    existing_names = existing_state.get(f"{cat_name}_names", set())
                    deleting_names = batch_deleting_names.get(cat_name, set())

                    raw_name = inp.get(name_field, "").strip()
                    if not raw_name:
                        break  # no name value to check — allow through

                    name_key = raw_name.lower() if name_case == "lower" else raw_name

                    if name_key in existing_names and name_key not in deleting_names:
                        skipped.setdefault(cat_name, []).append(raw_name)
                        logger.info(
                            "filter_duplicates: skipping '%s' — '%s' already exists.",
                            tool, raw_name,
                        )
                        skip = True
                    break  # each tool belongs to exactly one category — done

            if not skip:
                filtered.append(call)

        batch_data["calls"] = filtered

        # ── Build human-readable report ───────────────────────────────────────
        report_lines: list[str] = []
        for cat_name, names in skipped.items():
            label = cat_name.replace("_", " ")
            report_lines.append(
                f"  Skipped existing {label}(s) — reusing: {', '.join(names)}"
            )
        report_lines.extend(phantom_deletes)

        return batch_data, "\n".join(report_lines)

    async def fetch_created_elements(
        self,
        execute_tool_fn: Callable[[str, dict[str, Any]], Any],
        batch_data: dict,
        batch_result: dict,
    ) -> dict:
        """
        Fetch the actual Revit state for elements created (and deleted) in a batch.

        After execute_batch completes, individual create_* responses only contain
        an element_id.  This method bridges that gap by calling the relevant
        fetch_* tools and filtering down to elements belonging to the current batch.

        Returns a dict with:
          - One key per category (e.g. "grids", "columns") → list of matched items
          - "deleted_{cat}_ids" keys → list of successfully deleted element IDs
          - "failures" → list of failed tool-call entries
        """
        results: list[dict] = (
            batch_result.get("data", {}).get("results", [])
            if batch_result.get("status") == "success"
            else []
        )

        # ── Collect created element IDs by category ───────────────────────────
        created_ids: dict[str, set] = {}
        for res_item in results:
            tool = res_item.get("tool", "")
            eid  = res_item.get("result", {}).get("data", {}).get("element_id", "")
            if not eid:
                continue
            for cat_name, cfg in self._category_map.items():
                if tool == cfg.get("create_tool"):
                    created_ids.setdefault(cat_name, set()).add(eid)

        # ── Collect successfully deleted element IDs ──────────────────────────
        deleted_ids: dict[str, list] = {}
        for res_item in results:
            tool   = res_item.get("tool", "")
            status = res_item.get("result", {}).get("status", "")
            inp    = res_item.get("input", {})
            if status != "success":
                continue
            for cat_name, cfg in self._category_map.items():
                if tool == cfg.get("delete_tool"):
                    id_field = cfg["id_field"]
                    if id_field:
                        eid = inp.get(id_field, "")
                        if eid:
                            deleted_ids.setdefault(cat_name, []).append(eid)

        # ── Collect failures ──────────────────────────────────────────────────
        failures: list[dict] = []
        for res_item in results:
            if res_item.get("result", {}).get("status") == "error":
                failures.append({
                    "tool":    res_item.get("tool", ""),
                    "input":   res_item.get("input", {}),
                    "message": res_item.get("result", {}).get("message", ""),
                })
        if batch_result.get("status") == "error":
            failures.append({
                "tool":    "execute_batch",
                "input":   {},
                "message": batch_result.get("message", "Batch failed"),
            })

        # ── Fetch actual Revit state for created elements ─────────────────────
        output: dict = {"failures": failures}

        for cat_name, ids in created_ids.items():
            cfg        = self._category_map.get(cat_name, {})
            fetch_tool = cfg.get("fetch_tool")
            data_key   = cfg.get("data_key", cat_name)
            id_field   = cfg.get("id_field")

            if not fetch_tool:
                continue

            try:
                res = await execute_tool_fn(fetch_tool, {})
                all_items: list[dict] = res.get("data", {}).get(data_key, [])
                matched = (
                    [item for item in all_items if item.get(id_field, "") in ids]
                    if id_field else []
                )
                output[cat_name] = matched
                logger.info(
                    "fetch_created_elements: fetched %d %s, matched %d to batch creates.",
                    len(all_items), cat_name, len(matched),
                )
            except Exception as exc:
                logger.warning("fetch_created_elements: %s failed: %s", fetch_tool, exc)
                failures.append({"tool": fetch_tool, "input": {}, "message": str(exc)})

        # ── Add deleted ID lists to output ────────────────────────────────────
        for cat_name, ids in deleted_ids.items():
            output[f"deleted_{cat_name}_ids"] = ids

        return output

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_lookup_sets(self, state: dict, cat_name: str, cfg: dict) -> None:
        """
        Populate fast-lookup sets for a category from the fetched item list.

        Adds two optional keys to state:
          - "{cat_name}_names": set of (normalised) name strings for duplicate detection
          - "{cat_name}_ids":   set of id strings for phantom-delete validation
        """
        items      = state.get(cat_name, [])
        id_field   = cfg.get("id_field")
        name_field = cfg.get("name_field")
        name_case  = cfg.get("name_case", "lower")

        if id_field and items:
            state[f"{cat_name}_ids"] = {
                item.get(id_field, "")
                for item in items
                if item.get(id_field)
            }

        if name_field and items:
            if name_case == "lower":
                state[f"{cat_name}_names"] = {
                    item.get(name_field, "").strip().lower()
                    for item in items
                    if item.get(name_field)
                }
            else:
                state[f"{cat_name}_names"] = {
                    item.get(name_field, "").strip()
                    for item in items
                    if item.get(name_field)
                }

    @staticmethod
    def _format_item(item: dict, id_field: str | None) -> str:
        """
        Generic schema-agnostic item formatter.
        Dynamically builds a representation of any dictionary item by displaying
        key-value pairs of its primitive properties, ensuring new categories
        and properties are automatically surfaced without hardcoding.
        """
        parts: list[str] = []

        # 1. Promote name-like fields to the front
        name_keys = ("name", "mark", "new_type_name", "type_name", "label")
        name_val = None
        for k in name_keys:
            if item.get(k):
                name_val = item[k]
                break
        if name_val:
            parts.append(f"'{name_val}'")

        # 2. Formatted properties helper
        def format_val(v) -> str:
            if isinstance(v, dict):
                inner = [f"{ik}: {format_val(iv)}" for ik, iv in v.items()]
                return f"({', '.join(inner)})"
            return str(v)

        # 3. Dynamic fields
        skipped_keys = {id_field, "name", "mark", "new_type_name", "type_name", "label"}
        for k, v in item.items():
            if k in skipped_keys or v is None:
                continue

            if isinstance(v, (str, int, float, bool, dict)):
                if k.endswith("_id") or k.endswith("_ids"):
                    continue
                parts.append(f"{k.replace('_', ' ')}: {format_val(v)}")

        # 4. ID always last
        if id_field:
            id_val = item.get(id_field)
            if id_val:
                parts.append(f"ID: '{id_val}'")

        return " ".join(parts) if parts else str(item)

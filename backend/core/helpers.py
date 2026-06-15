# -*- coding: utf-8 -*-
"""
helpers.py — Lightweight utility functions for the agent pipeline.

The heavier state-management functions (fetch_existing_state, format_summary,
inject_context, filter_duplicates, fetch_created_elements) have been migrated
to core.state_manager.ModelStateManager for a cohesive, schema-driven OOP design.

This module retains only inject_schemas_context, which is a pure formatting
utility that does not require category-level awareness.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def inject_schemas_context(
    history: list[dict],
    tool_schemas: list[dict],
) -> list[dict]:
    """
    Format and inject available tool schemas as a system-role message.

    Gives the clarifier, designer, planner, parser, and validator
    complete structural details of the available Revit APIs.
    """
    if not tool_schemas:
        return list(history)

    schema_summary = [
        {
            "name": ts["name"],
            "description": ts.get("description", ""),
            "parameters": ts.get("parameters", {}),
        }
        for ts in tool_schemas
    ]

    note = (
        "AVAILABLE REVIT TOOLS AND SCHEMAS:\n"
        "Use this context to check parameters, design layout tables, "
        "formulate plans, translate JSON payloads, and validate properties.\n"
        f"```json\n{json.dumps(schema_summary, indent=2)}\n```"
    )
    return list(history) + [{"role": "system", "content": note}]

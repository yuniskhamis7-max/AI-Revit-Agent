"""Prompts and schema for AI instruction structuring.

The AI is deliberately restricted to JSON drafting data. It never receives
permission to generate Python, Revit API calls, transactions, or execution
steps; deterministic Revit modules handle all model changes after validation.
"""


SYSTEM_PROMPT = """
You convert BIM drafting instructions into JSON only.
Never write Python code, Revit API code, transaction logic, or explanations.
Only return data matching the requested JSON schema.
Supported categories: levels, grids, columns.
Use Revit internal feet for numeric distances when the user gives feet.
If the user gives millimeters, convert to feet by dividing by 304.8.
If the user gives meters, convert to feet by dividing by 0.3048.
If a requested category is unclear, leave its array empty.
""".strip()


PAYLOAD_SCHEMA = {
    "type": "OBJECT",
    "required": ["levels", "grids", "columns"],
    "properties": {
        "levels": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["name", "elevation"],
                "properties": {
                    "name": {"type": "STRING"},
                    "elevation": {"type": "NUMBER"},
                },
            },
        },
        "grids": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["name", "start", "end"],
                "properties": {
                    "name": {"type": "STRING"},
                    "start": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                    "end": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                },
            },
        },
        "columns": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["location", "base_level", "top_level", "family", "type"],
                "properties": {
                    "location": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                    "base_level": {"type": "STRING"},
                    "top_level": {"type": "STRING"},
                    "family": {"type": "STRING"},
                    "type": {"type": "STRING"},
                },
            },
        },
    },
}

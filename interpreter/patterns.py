"""Controlled grammar patterns for deterministic BIM instructions."""

import re


CREATE_LEVELS_SPACED = re.compile(
    r"^create\s+(?P<count>\d+)\s+levels?\s+spaced\s+"
    r"(?P<spacing>-?\d+(?:\.\d+)?)\s*(?P<unit>mm|m|ft)?\s+apart$",
    re.IGNORECASE,
)

CREATE_LEVEL_AT = re.compile(
    r"^create\s+(?P<name>level\s+\w+)\s+at\s+elevation\s+"
    r"(?P<elevation>-?\d+(?:\.\d+)?)\s*(?P<unit>mm|m|ft)?$",
    re.IGNORECASE,
)

CREATE_GRIDS_NAMED = re.compile(
    r"^create\s+grids?\s+(?P<names>[a-z0-9,\sand]+)$",
    re.IGNORECASE,
)

CREATE_GRID_FROM_TO = re.compile(
    r"^create\s+grid\s+(?P<name>[a-z0-9]+)\s+from\s+"
    r"(?P<x1>-?\d+(?:\.\d+)?),(?P<y1>-?\d+(?:\.\d+)?)\s+to\s+"
    r"(?P<x2>-?\d+(?:\.\d+)?),(?P<y2>-?\d+(?:\.\d+)?)\s*(?P<unit>mm|m|ft)?$",
    re.IGNORECASE,
)

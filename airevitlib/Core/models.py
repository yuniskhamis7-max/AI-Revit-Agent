# airevitlib/core/models.py
from dataclasses import dataclass, field
from typing import List

@dataclass
class Point2D:
    x: float  # Revit internal decimal feet
    y: float  # Revit internal decimal feet

@dataclass
class LevelModel:
    id: str
    name: str
    elevation: float  # Revit internal decimal feet
    is_pinned: bool = True
    create_floor_plan: bool = True

@dataclass
class GridModel:
    id: str
    name: str
    start: Point2D
    end: Point2D
    is_pinned: bool = True

@dataclass
class ProjectSettings:
    source_units: str = "mm"
    coordinate_system: str = "project_base_point"

@dataclass
class CompiledProjectData:
    settings: ProjectSettings
    levels: List[LevelModel] = field(default_factory=list)
    grids: List[GridModel] = field(default_factory=list)
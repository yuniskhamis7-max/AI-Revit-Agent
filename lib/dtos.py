# dtos.py
import math
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Point2D:
    x: float
    y: float
    
    def distance_to(self, other: 'Point2D') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

@dataclass
class LevelData:
    id: str  # Stable ID for database syncing
    name: str
    elevation: float
    is_pinned: bool = True
    create_floor_plan: bool = True

@dataclass
class GridData:
    id: str  # Stable ID for database syncing
    name: str
    start: Point2D
    end: Point2D
    is_pinned: bool = True

@dataclass
class LevelStrategy:
    mode: str = "explicit"  # "explicit" or "link"
    link_name: Optional[str] = None
    prefix_copied_levels: str = ""

@dataclass
class GridStrategy:
    mode: str = "explicit"  # "explicit" or "link"
    link_name: Optional[str] = None
    prefix_copied_grids: str = ""

@dataclass
class ProjectSettings:
    grids_unit: str = "m"   
    levels_unit: str = "m"  
    # "project_base_point", "survey_point", or "internal_origin"
    coordinate_system: str = "project_base_point"

@dataclass
class ProjectData:
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    level_strategy: LevelStrategy = field(default_factory=LevelStrategy)
    grid_strategy: GridStrategy = field(default_factory=GridStrategy)
    levels: List[LevelData] = field(default_factory=list)
    grids: List[GridData] = field(default_factory=list)
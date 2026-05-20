import math
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Point2D:
    x: float
    y: float

    def distance_to(self, other: 'Point2D') -> float:
        """Helper to calculate distance between two points."""
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

@dataclass
class LevelData:
    name: str
    elevation: float
    is_pinned: bool = True
    create_floor_plan: bool = True

@dataclass
class GridData:
    name: str
    start: Point2D
    end: Point2D
    is_pinned: bool = True

@dataclass
class ProjectData:
    """The master schema representing the entire AI payload."""
    levels: List[LevelData] = field(default_factory=list)
    grids: List[GridData] = field(default_factory=list)
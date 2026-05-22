# revit_managers/grid_manager.py
import Autodesk.Revit.DB as DB
from typing import Optional
from dtos import GridData
from coordinate_utility import CoordinateUtility

class GridManager:
    TRACKING_PREFIX = "AI_ID:GRD:"

    def __init__(self, doc: DB.Document, coord_utility: CoordinateUtility):
        self.doc = doc
        self.coord_utility = coord_utility
        self._grid_cache = self._build_grid_cache()
        self.lowest_elevation = self._get_lowest_level_elevation()

    def _get_lowest_level_elevation(self) -> float:
        """Strategy 1: Identifies the lowest level elevation to project the horizontal grid line."""
        levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
        if levels:
            return min([lvl.Elevation for lvl in levels])
        return 0.0

    def _build_grid_cache(self):
        """Strategy 4: Indexes cached grid elements using the tracking ID inside standard Comments."""
        cache = {}
        grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).ToElements()
        for grid in grids:
            tracking_id = self._get_tracking_id(grid)
            if tracking_id:
                cache[tracking_id] = grid
            else:
                cache[grid.Name] = grid
        return cache

    def _get_tracking_id(self, grid: DB.Grid) -> Optional[str]:
        param = grid.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param and param.HasValue and param.AsString().startswith(self.TRACKING_PREFIX):
            return param.AsString().replace(self.TRACKING_PREFIX, "")
        return None

    def _set_tracking_id(self, grid: DB.Grid, element_id: str):
        param = grid.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param:
            param.Set(f"{self.TRACKING_PREFIX}{element_id}")

    def process_from_payload(self, grid_data: GridData) -> DB.Grid:
        # Match using tracking identifier, falling back to name
        existing_grid = self._grid_cache.get(grid_data.id) or self._grid_cache.get(grid_data.name)
        if existing_grid:
            if existing_grid.Name != grid_data.name:
                try: 
                    existing_grid.Name = grid_data.name
                except: 
                    pass
            self.pin(existing_grid, grid_data.is_pinned)
            return existing_grid

        # Strategy 1: Place grid curve on the lowest project elevation plane
        start_xyz = self.coord_utility.transform_point(grid_data.start.x, grid_data.start.y, self.lowest_elevation)
        end_xyz = self.coord_utility.transform_point(grid_data.end.x, grid_data.end.y, self.lowest_elevation)

        try:
            line = DB.Line.CreateBound(start_xyz, end_xyz)
            new_grid = DB.Grid.Create(self.doc, line)
            
            try:
                new_grid.Name = grid_data.name
            except:
                pass 
            
            self._set_tracking_id(new_grid, grid_data.id)
            self.pin(new_grid, grid_data.is_pinned)
            
            self._grid_cache[grid_data.id] = new_grid
            return new_grid
            
        except Exception as e:
            print(f"Error creating Grid '{grid_data.name}': {e}")
            return None

    def pin(self, grid: DB.Grid, state: bool = True):
        if grid and grid.Pinned != state:
            grid.Pinned = state
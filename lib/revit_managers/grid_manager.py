import Autodesk.Revit.DB as DB
from dtos import GridData

class GridManager:
    MINIMUM_LINE_LENGTH = 0.004 

    def __init__(self, doc: DB.Document, use_pbp: bool = True):
        self.doc = doc
        self.use_pbp = use_pbp
        self._grid_cache = self._build_grid_cache()
        self.base_offset = self._get_pbp_offset() if use_pbp else DB.XYZ.Zero

    def _get_pbp_offset(self) -> DB.XYZ:
        pbp_col = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint).WhereElementIsNotElementType().FirstElement()
        if pbp_col:
            bbox = pbp_col.get_BoundingBox(None)
            if bbox:
                return DB.XYZ(bbox.Min.X, bbox.Min.Y, 0.0)
        return DB.XYZ.Zero

    def _build_grid_cache(self):
        grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).ToElements()
        return {grid.Name: grid for grid in grids}

    def process_from_payload(self, grid_data: GridData) -> DB.Grid:
        existing_grid = self._grid_cache.get(grid_data.name)
        if existing_grid:
            self.pin(existing_grid, grid_data.is_pinned)
            return existing_grid

        start_xyz = DB.XYZ(grid_data.start.x, grid_data.start.y, 0.0) + self.base_offset
        end_xyz = DB.XYZ(grid_data.end.x, grid_data.end.y, 0.0) + self.base_offset

        try:
            line = DB.Line.CreateBound(start_xyz, end_xyz)
            new_grid = DB.Grid.Create(self.doc, line)
            
            try:
                new_grid.Name = grid_data.name
            except:
                pass 
            
            self.pin(new_grid, grid_data.is_pinned)
            self._grid_cache[new_grid.Name] = new_grid
            return new_grid
            
        except Exception as e:
            print(f"Error creating Grid '{grid_data.name}': {e}")
            return None

    def pin(self, grid: DB.Grid, state: bool = True):
        if grid and grid.Pinned != state:
            grid.Pinned = state
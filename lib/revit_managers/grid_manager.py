import Autodesk.Revit.DB as DB
from dtos import GridData, Point2D

class GridManager:
    """Defensive toolkit for Revit Grid generation. Prevents destructive overwrites."""
    
    MINIMUM_LINE_LENGTH = 0.004 

    def __init__(self, doc: DB.Document):
        self.doc = doc
        self._grid_cache = self._build_grid_cache()

    def _build_grid_cache(self):
        grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).ToElements()
        return {grid.Name: grid for grid in grids}

    def process_from_payload(self, grid_data: GridData) -> DB.Grid:
        """Safely creates grids, bypassing if they already exist to protect dimensions."""
        existing_grid = self._grid_cache.get(grid_data.name)

        if existing_grid:
            self.pin(existing_grid, grid_data.is_pinned)
            return existing_grid

        dist = grid_data.start.distance_to(grid_data.end)
        if dist < self.MINIMUM_LINE_LENGTH:
            print(f"ERROR: Points too close for Grid '{grid_data.name}'. Skipped.")
            return None

        new_grid = self.create(grid_data.name, grid_data.start, grid_data.end)
        if new_grid:
            self.pin(new_grid, grid_data.is_pinned)
            
        return new_grid

    def create(self, name: str, start: Point2D, end: Point2D) -> DB.Grid:
        start_xyz = DB.XYZ(start.x, start.y, 0.0)
        end_xyz = DB.XYZ(end.x, end.y, 0.0)

        try:
            line = DB.Line.CreateBound(start_xyz, end_xyz)
            new_grid = DB.Grid.Create(self.doc, line)
            
            try:
                new_grid.Name = name
            except Exception as e:
                pass # Accept default Revit naming if conflict occurs

            self._grid_cache[new_grid.Name] = new_grid
            return new_grid
            
        except Exception as e:
            print(f"Fatal error creating Grid '{name}': {e}")
            return None

    def pin(self, grid: DB.Grid, state: bool = True):
        if grid and grid.Pinned != state:
            grid.Pinned = state

    def rename(self, grid: DB.Grid, new_name: str):
        if new_name in self._grid_cache:
            raise ValueError(f"A grid named '{new_name}' already exists.")
        
        self._grid_cache.pop(grid.Name, None)
        grid.Name = new_name
        self._grid_cache[new_name] = grid

    def force_recreate(self, grid_data: GridData):
        """DANGER: Wipes grid and attached dimensions to recreate from scratch."""
        existing_grid = self._grid_cache.get(grid_data.name)
        if existing_grid:
            self.doc.Delete(existing_grid.Id)
            self._grid_cache.pop(grid_data.name, None)
        return self.process_from_payload(grid_data)
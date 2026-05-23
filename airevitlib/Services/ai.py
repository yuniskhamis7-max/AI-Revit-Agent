# airevitlib/revit/elements.py
import Autodesk.Revit.DB as DB
import random
from typing import Optional, Dict
from core.models import LevelModel, GridModel
from revit.coordinates import CoordinateUtility

class StructuralManager:
    """Manages transactional database writes, element modifications, and deletions."""
    
    LVL_PREFIX = "AI_ID:LVL:"
    GRD_PREFIX = "AI_ID:GRD:"

    def __init__(self, doc: DB.Document, coord_utility: CoordinateUtility):
        self.doc = doc
        self.coord = coord_utility
        self._levels = self._cache_existing_elements(DB.Level, self.LVL_PREFIX)
        self._grids = self._cache_existing_elements(DB.Grid, self.GRD_PREFIX)

    def get_existing_model_context(self) -> dict:
        """Serializes current Revit model elements so the AI can run differential audits."""
        return {
            "levels": [
                {"id": self._get_tracking_id(lvl, self.LVL_PREFIX) or lvl.Name, "name": lvl.Name, "elevation_m": lvl.Elevation / 3.280839895}
                for lvl in self._levels.values()
            ],
            "grids": [
                {
                    "id": self._get_tracking_id(grd, self.GRD_PREFIX) or grd.Name, 
                    "name": grd.Name,
                    "axis": self._get_grid_properties(grd)[0],
                    "position_m": self._get_grid_properties(grd)[1]
                }
                for grd in self._grids.values()
            ]
        }

    def _get_grid_properties(self, grid: DB.Grid) -> tuple:
        """Returns the axis ('X' or 'Y') and position (in meters) of a grid line relative to origin."""
        try:
            curve = grid.Curve
            if curve and isinstance(curve, DB.Line):
                start = curve.GetEndPoint(0)
                end = curve.GetEndPoint(1)
                direction = end - start
                
                # Check orientation relative to model space
                if abs(direction.X) < 0.001:
                    # Vertical grid line (spaced along X axis, so X coordinate is constant)
                    rel_x = (start.X - self.coord.translation.X) / 3.280839895
                    return "X", rel_x
                else:
                    # Horizontal grid line (spaced along Y axis, so Y coordinate is constant)
                    rel_y = (start.Y - self.coord.translation.Y) / 3.280839895
                    return "Y", rel_y
        except Exception as ex:
            print("Warning: Could not extract properties for grid {}: {}".format(grid.Name, ex))
        return "X", 0.0

    def _cache_existing_elements(self, db_class, tracking_prefix: str) -> Dict[str, DB.Element]:
        cache = {}
        elements = DB.FilteredElementCollector(self.doc).OfClass(db_class).WhereElementIsNotElementType().ToElements()
        for elem in elements:
            tracking_id = self._get_tracking_id(elem, tracking_prefix)
            if tracking_id:
                cache[tracking_id] = elem
            else:
                cache[elem.Name] = elem
        return cache

    def _get_tracking_id(self, elem: DB.Element, prefix: str) -> Optional[str]:
        param = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param and param.HasValue and param.AsString().startswith(prefix):
            return param.AsString().replace(prefix, "")
        return None

    def _set_tracking_id(self, elem: DB.Element, prefix: str, target_id: str):
        param = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param:
            param.Set(f"{prefix}{target_id}")

    def element_exists(self, element_id: str, name: str, element_type: str) -> bool:
        cache = self._levels if element_type == "level" else self._grids
        return (element_id in cache) or (name in cache)

    def get_existing_elevation(self, element_id: str, name: str) -> Optional[float]:
        elem = self._levels.get(element_id) or self._levels.get(name)
        return elem.Elevation if elem else None

    def prepare_deletions(self, delete_ids: list, element_type: str) -> list:
        """Temporarily renames all matching elements flagged for deletion and removes them from active caches."""
        cache = self._levels if element_type == "level" else self._grids
        elements_to_delete = []
        
        # Gather all elements of this type in the document to safely clean up duplicates
        db_class = DB.Level if element_type == "level" else DB.Grid
        prefix = self.LVL_PREFIX if element_type == "level" else self.GRD_PREFIX
        all_elements = DB.FilteredElementCollector(self.doc) \
            .OfClass(db_class) \
            .WhereElementIsNotElementType() \
            .ToElements()

        for elem in all_elements:
            if not elem.IsValidObject:
                continue
            
            tracking_id = self._get_tracking_id(elem, prefix)
            name = elem.Name
            
            if (tracking_id in delete_ids) or (name in delete_ids):
                try:
                    elem.Pinned = False
                    rand_suffix = random.randint(10000, 99999)
                    temp_name = "ToDelete_{}_{}".format(element_type, rand_suffix)
                    elem.Name = temp_name
                except Exception as ex:
                    print("Warning: Could not temporarily rename {} '{}': {}".format(element_type, name, ex))
                
                elements_to_delete.append(elem)
                
                # Pop out of the cache so we do not match or update them during the creation phase
                if tracking_id in cache:
                    cache.pop(tracking_id, None)
                if name in cache:
                    cache.pop(name, None)
                    
        return elements_to_delete

    def execute_deletions(self, elements_to_delete: list):
        """Safely unpins and deletes levels or grids from the model, printing brief warnings on protected elements."""
        for elem in elements_to_delete:
            if elem and elem.IsValidObject:
                try:
                    elem.Pinned = False
                    self.doc.Delete(elem.Id)
                except Exception as ex:
                    # Clean up the console output by showing only the first line of the .NET exception
                    err_msg = str(ex).split('\n')[0]
                    print("Info: Element {} was kept (protected by Revit database). details: {}".format(elem.Id, err_msg))

    def process_level(self, data: LevelModel) -> DB.Level:
        p_xyz = self.coord.transform_point(0.0, 0.0, data.elevation, is_level=True)
        target_z = p_xyz.Z

        existing = self._levels.get(data.id) or self._levels.get(data.name)
        if existing:
            existing.Pinned = False
            if abs(existing.Elevation - target_z) > 0.001:
                existing.Elevation = target_z
            if existing.Name != data.name:
                existing.Name = data.name
            level = existing
        else:
            level = DB.Level.Create(self.doc, target_z)
            level.Name = data.name

        self._set_tracking_id(level, self.LVL_PREFIX, data.id)
        level.Pinned = data.is_pinned
        return level

    def process_grid(self, data: GridModel, base_elevation: float) -> DB.Grid:
        existing = self._grids.get(data.id) or self._grids.get(data.name)
        if existing:
            try:
                # We recreate grid lines to ensure their lengths always match our compiled extents
                existing.Pinned = False
                self.doc.Delete(existing.Id)
            except Exception as err:
                err_msg = str(err).split('\n')[0]
                print("Warning: Failed to delete existing grid {} before recreating: {}".format(existing.Name, err_msg))

        start_xyz = self.coord.transform_point(data.start.x, data.start.y, base_elevation)
        end_xyz = self.coord.transform_point(data.end.x, data.end.y, base_elevation)

        try:
            line = DB.Line.CreateBound(start_xyz, end_xyz)
            grid = DB.Grid.Create(self.doc, line)
            grid.Name = data.name
            self._set_tracking_id(grid, self.GRD_PREFIX, data.id)
            grid.Pinned = data.is_pinned
            return grid
        except Exception as err:
            print(f"Failed to create grid {data.name}: {err}")
            return None
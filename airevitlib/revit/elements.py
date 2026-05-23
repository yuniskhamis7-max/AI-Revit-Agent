# airevitlib/revit/elements.py
import Autodesk.Revit.DB as DB
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
                {"id": self._get_tracking_id(grd, self.GRD_PREFIX) or grd.Name, "name": grd.Name}
                for grd in self._grids.values()
            ]
        }

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

    def execute_deletions(self, delete_ids: list, element_type: str):
        """Safely unpins and deletes levels or grids from the model."""
        cache = self._levels if element_type == "level" else self._grids
        for key in delete_ids:
            elem = cache.get(key)
            if elem and elem.IsValidObject:
                elem.Pinned = False
                self.doc.Delete(elem.Id)

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
            # We recreate grid lines to ensure their lengths always match our compiled extents
            existing.Pinned = False
            self.doc.Delete(existing.Id)

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
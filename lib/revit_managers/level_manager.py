import Autodesk.Revit.DB as DB
from typing import Optional
from dtos import LevelData

class LevelManager:
    """A robust toolkit for Revit Level generation and manipulation."""
    
    def __init__(self, doc: DB.Document):
        self.doc = doc
        self._level_cache = self._build_level_cache()
        self._view_family_types = self._get_view_family_types()

    def _build_level_cache(self):
        levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
        return {lvl.Name: lvl for lvl in levels}

    def _get_view_family_types(self):
        vft_collector = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewFamilyType).ToElements()
        return {vft.ViewFamily: vft for vft in vft_collector}

    def process_from_payload(self, level_data: LevelData) -> DB.Level:
        """Intelligently creates or updates a Level based on AI data."""
        existing_level = self._level_cache.get(level_data.name)

        if existing_level:
            self.offset_to_elevation(existing_level, level_data.elevation)
            level = existing_level
        else:
            level = self.create(level_data.name, level_data.elevation)

        self.pin(level, level_data.is_pinned)
        
        if level_data.create_floor_plan:
            self.create_plan_view(level, DB.ViewFamily.FloorPlan)

        return level

    def create(self, name: str, elevation: float) -> DB.Level:
        new_level = DB.Level.Create(self.doc, elevation)
        new_level.Name = name
        self._level_cache[name] = new_level 
        return new_level

    def rename(self, level: DB.Level, new_name: str):
        if new_name in self._level_cache:
            raise ValueError(f"Cannot rename. Level '{new_name}' already exists.")
        self._level_cache.pop(level.Name, None)
        level.Name = new_name
        self._level_cache[new_name] = level

    def offset_to_elevation(self, level: DB.Level, target_elevation: float):
        if abs(level.Elevation - target_elevation) > 0.001:
            level.Elevation = target_elevation

    def pin(self, level: DB.Level, state: bool = True):
        if level.Pinned != state:
            level.Pinned = state

    def delete(self, level: DB.Level, force: bool = False):
        if not force:
            print(f"WARNING: Skipping deletion of '{level.Name}'. Use force=True.")
            return
        self.doc.Delete(level.Id)
        self._level_cache.pop(level.Name, None)

    def create_plan_view(self, level: DB.Level, view_family: DB.ViewFamily) -> Optional[DB.ViewPlan]:
        view_type = self._view_family_types.get(view_family)
        if not view_type:
            return None

        existing_views = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewPlan).ToElements()
        for view in existing_views:
            if view.GenLevel and view.GenLevel.Id == level.Id and view.GetTypeId() == view_type.Id:
                return view 

        return DB.ViewPlan.Create(self.doc, view_type.Id, level.Id)
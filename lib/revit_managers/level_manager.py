import Autodesk.Revit.DB as DB
from typing import Optional
from dtos import LevelData

class LevelManager:
    def __init__(self, doc: DB.Document, use_pbp: bool = True):
        self.doc = doc
        self.use_pbp = use_pbp
        self._level_cache = self._build_level_cache()
        self._view_family_types = self._get_view_family_types()
        self.base_elevation_offset = self._get_pbp_elevation() if use_pbp else 0.0

    def _get_pbp_elevation(self) -> float:
        pbp_col = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint).WhereElementIsNotElementType().FirstElement()
        if pbp_col:
            bbox = pbp_col.get_BoundingBox(None)
            if bbox: return bbox.Min.Z
        return 0.0

    def _build_level_cache(self):
        levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
        return {lvl.Name: lvl for lvl in levels}

    def _get_view_family_types(self):
        vft_col = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewFamilyType).ToElements()
        return {vft.ViewFamily: vft for vft in vft_col}

    def process_from_payload(self, level_data: LevelData) -> DB.Level:
        target_elev = level_data.elevation + self.base_elevation_offset
        existing_level = self._level_cache.get(level_data.name)

        if existing_level:
            if abs(existing_level.Elevation - target_elev) > 0.001:
                existing_level.Elevation = target_elev
            level = existing_level
        else:
            level = DB.Level.Create(self.doc, target_elev)
            level.Name = level_data.name
            self._level_cache[level.Name] = level
        
        self.pin(level, level_data.is_pinned)
        
        if level_data.create_floor_plan:
            self.create_plan_view(level, DB.ViewFamily.FloorPlan)

        return level

    def pin(self, level: DB.Level, state: bool = True):
        if level.Pinned != state:
            level.Pinned = state

    def create_plan_view(self, level: DB.Level, view_family: DB.ViewFamily) -> Optional[DB.ViewPlan]:
        view_type = self._view_family_types.get(view_family)
        if not view_type: return None

        existing_views = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewPlan).ToElements()
        for view in existing_views:
            if view.GenLevel and view.GenLevel.Id == level.Id and view.GetTypeId() == view_type.Id:
                return view 

        return DB.ViewPlan.Create(self.doc, view_type.Id, level.Id)
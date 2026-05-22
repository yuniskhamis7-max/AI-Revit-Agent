# revit_managers/level_manager.py
import Autodesk.Revit.DB as DB
from typing import Optional
from dtos import LevelData
from coordinate_utility import CoordinateUtility

class LevelManager:
    TRACKING_PREFIX = "AI_ID:LVL:"

    def __init__(self, doc: DB.Document, coord_utility: CoordinateUtility):
        self.doc = doc
        self.coord_utility = coord_utility
        self._level_cache = self._build_level_cache()
        self._view_family_types = self._get_view_family_types()

    def _build_level_cache(self):
        """Caches elements using our persistent tracking ID instead of Name (Strategy 4)."""
        cache = {}
        levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
        for lvl in levels:
            tracking_id = self._get_tracking_id(lvl)
            if tracking_id:
                cache[tracking_id] = lvl
            else:
                # Fallback to Name if it hasn't been tagged by our tool yet
                cache[lvl.Name] = lvl
        return cache

    def _get_tracking_id(self, level: DB.Level) -> Optional[str]:
        param = level.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param and param.HasValue and param.AsString().startswith(self.TRACKING_PREFIX):
            return param.AsString().replace(self.TRACKING_PREFIX, "")
        return None

    def _set_tracking_id(self, level: DB.Level, element_id: str):
        param = level.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param:
            param.Set(f"{self.TRACKING_PREFIX}{element_id}")

    def _get_view_family_types(self):
        vft_col = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewFamilyType).ToElements()
        return {vft.ViewFamily: vft for vft in vft_col}

    def process_from_payload(self, level_data: LevelData) -> DB.Level:
        # Resolve target coordinate Z value via our math-based utility
        transformed_point = self.coord_utility.transform_point(0.0, 0.0, level_data.elevation)
        target_elev = transformed_point.Z

        # Attempt tracking match via unique Stable ID first, then fallback to Name
        existing_level = self._level_cache.get(level_data.id) or self._level_cache.get(level_data.name)

        if existing_level:
            if abs(existing_level.Elevation - target_elev) > 0.001:
                existing_level.Elevation = target_elev
            if existing_level.Name != level_data.name:
                existing_level.Name = level_data.name
            level = existing_level
        else:
            level = DB.Level.Create(self.doc, target_elev)
            level.Name = level_data.name
        
        # Write tracking ID to comments parameter
        self._set_tracking_id(level, level_data.id)
        self.pin(level, level_data.is_pinned)
        
        # Update cache mapping
        self._level_cache[level_data.id] = level

        if level_data.create_floor_plan:
            self.create_plan_view(level, DB.ViewFamily.FloorPlan)

        return level

    def pin(self, level: DB.Level, state: bool = True):
        if level.Pinned != state:
            level.Pinned = state

    def create_plan_view(self, level: DB.Level, view_family: DB.ViewFamily) -> Optional[DB.ViewPlan]:
        view_type = self._view_family_types.get(view_family)
        if not view_type: 
            return None

        existing_views = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewPlan).ToElements()
        for view in existing_views:
            if view.GenLevel and view.GenLevel.Id == level.Id and view.GetTypeId() == view_type.Id:
                return view 

        return DB.ViewPlan.Create(self.doc, view_type.Id, level.Id)
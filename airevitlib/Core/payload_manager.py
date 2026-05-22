# airevitlib/core/payload_manager.py
import json
from dtos import Point2D, LevelData, GridData, ProjectData, ProjectSettings, GridStrategy, LevelStrategy

class PayloadManager:
    UNIT_MULTIPLIERS = {
        "m": 3.280839895,
        "mm": 0.0032808399,
        "cm": 0.032808399,
        "ft": 1.0,
        "in": 0.0833333333
    }

    def __init__(self, raw_json_string: str):
        self.raw_json = raw_json_string
        self.project_data = self._parse_payload(raw_json_string)

    def _convert(self, val: float, unit: str) -> float:
        multiplier = self.UNIT_MULTIPLIERS.get(unit.lower(), 1.0)
        return val * multiplier

    def _parse_payload(self, json_str: str) -> ProjectData:
        try:
            data = json.loads(json_str)
            
            s_data = data.get("settings", {})
            settings = ProjectSettings(
                grids_unit=s_data.get("grids_unit", "m"),
                levels_unit=s_data.get("levels_unit", "m"),
                coordinate_system=s_data.get("coordinate_system", "project_base_point")
            )

            level_strategy = LevelStrategy(**data.get("level_strategy", {}))
            grid_strategy = GridStrategy(**data.get("grid_strategy", {}))

            levels = []
            for lvl in data.get("levels", []):
                elev = self._convert(lvl["elevation"], settings.levels_unit)
                lvl_id = lvl.get("id", "lvl_" + lvl["name"].lower().replace(" ", "_"))
                levels.append(LevelData(
                    id=lvl_id,
                    name=lvl["name"], 
                    elevation=elev, 
                    is_pinned=lvl.get("is_pinned", True),
                    create_floor_plan=lvl.get("create_floor_plan", True)
                ))
            
            grids = []
            for grd in data.get("grids", []):
                sx = self._convert(grd["start"]["x"], settings.grids_unit)
                sy = self._convert(grd["start"]["y"], settings.grids_unit)
                ex = self._convert(grd["end"]["x"], settings.grids_unit)
                ey = self._convert(grd["end"]["y"], settings.grids_unit)
                
                grd_id = grd.get("id", "grid_" + grd["name"].lower().replace(" ", "_"))
                grids.append(GridData(
                    id=grd_id,
                    name=grd["name"], 
                    start=Point2D(sx, sy), 
                    end=Point2D(ex, ey),
                    is_pinned=grd.get("is_pinned", True)
                ))
                
            return ProjectData(
                settings=settings, 
                level_strategy=level_strategy,
                grid_strategy=grid_strategy, 
                levels=levels, 
                grids=grids
            )
            
        except Exception as e:
            raise ValueError(f"Payload parsing failed: {e}")
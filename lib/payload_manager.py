import json
from dtos import Point2D, LevelData, GridData, ProjectData, ProjectSettings, GridStrategy, LevelStrategy
from typing import List

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
                use_project_base_point=s_data.get("use_project_base_point", True)
            )

            # Strategies
            l_strat_data = data.get("level_strategy", {})
            level_strategy = LevelStrategy(**l_strat_data)

            g_strat_data = data.get("grid_strategy", {})
            grid_strategy = GridStrategy(**g_strat_data)

            levels = []
            for lvl in data.get("levels", []):
                elev = self._convert(lvl["elevation"], settings.levels_unit)
                levels.append(LevelData(
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
                
                grids.append(GridData(
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
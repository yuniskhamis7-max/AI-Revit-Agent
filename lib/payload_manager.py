import json
from dtos import Point2D, LevelData, GridData, ProjectData
from typing import List

class PayloadManager:
    """Validates and parses raw AI JSON into strictly typed Data Objects."""
    
    def __init__(self, raw_json_string: str):
        self.raw_json = raw_json_string
        self.project_data = self._parse_payload(raw_json_string)

    def _parse_payload(self, json_str: str) -> ProjectData:
        try:
            data = json.loads(json_str)
            
            # Parse Levels safely
            levels = [LevelData(**lvl) for lvl in data.get("levels", [])]
            
            # Parse Grids (handling nested dictionaries)
            grids = []
            for grd in data.get("grids", []):
                start_pt = Point2D(**grd["start"])
                end_pt = Point2D(**grd["end"])
                grids.append(
                    GridData(
                        name=grd["name"], 
                        start=start_pt, 
                        end=end_pt,
                        is_pinned=grd.get("is_pinned", True)
                    )
                )
                
            return ProjectData(levels=levels, grids=grids)
            
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format received from AI. Check syntax.")
        except Exception as e:
            raise ValueError(f"Data mapping error. AI JSON does not match expected schema: {e}")

    # --- GETTERS ---
    def get_levels(self) -> List[LevelData]:
        return self.project_data.levels

    def get_grids(self) -> List[GridData]:
        return self.project_data.grids
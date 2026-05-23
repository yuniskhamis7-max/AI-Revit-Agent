# airevitlib/services/compiler.py
from core.models import CompiledProjectData, ProjectSettings, LevelModel, GridModel, Point2D

class DirectUnitCompiler:
    """Calculates building extents and scales coordinates to internal decimal feet."""
    
    TO_FEET = {
        "m": 3.280839895,
        "mm": 0.0032808399,
        "cm": 0.032808399,
        "ft": 1.0,
        "in": 0.0833333333
    }

    def __init__(self, raw_ai_response: dict, existing_context: dict = None):
        self.ai_data = raw_ai_response
        self.delta = raw_ai_response.get("proposed_delta", {})
        self.existing = existing_context or {"levels": [], "grids": []}
        self.unit = "m"  # Standardize on meters for internal transfer scale
        self.scale = self.TO_FEET[self.unit]

    def compile(self) -> CompiledProjectData:
        settings = ProjectSettings(
            source_units=self.unit,
            coordinate_system="project_base_point"
        )
        
        levels = self._compile_levels()
        grids = self._compile_grids()
        
        return CompiledProjectData(
            settings=settings,
            levels=levels,
            grids=grids
        )

    def _compile_levels(self) -> list:
        compiled = []
        creates = self.delta.get("levels", {}).get("create", [])
        updates = self.delta.get("levels", {}).get("update", [])
        
        for l in (creates + updates):
            compiled.append(LevelModel(
                id=l["id"],
                name=l["name"],
                elevation=float(l["elevation"]) * self.scale,
                is_pinned=True,
                create_floor_plan=l.get("create_floor_plan", True)
            ))
        return compiled

    def _compile_grids(self) -> list:
        # 1. Gather all target grid elements to compile
        # We start with proposed creations and updates from the AI's delta payload
        grid_data_list = []
        delta_ids = set()
        
        creates = self.delta.get("grids", {}).get("create", [])
        updates = self.delta.get("grids", {}).get("update", [])
        deletes = set(self.delta.get("grids", {}).get("delete", []))

        for g in (creates + updates):
            grid_data_list.append({
                "id": g["id"],
                "name": g["name"],
                "axis": g["axis"].upper(),
                "position": float(g["position"])
            })
            delta_ids.add(g["id"])
            delta_ids.add(g["name"])

        # 2. Add preserved grids (grids currently in Revit that are not being modified or deleted)
        for g in self.existing.get("grids", []):
            g_id = g["id"]
            g_name = g["name"]
            
            if g_id not in deletes and g_name not in deletes and g_id not in delta_ids and g_name not in delta_ids:
                grid_data_list.append({
                    "id": g_id,
                    "name": g_name,
                    "axis": g.get("axis", "X").upper(),
                    "position": float(g.get("position_m", 0.0))
                })

        # If there are no grids combined, return empty immediately
        if not grid_data_list:
            return []

        # 3. Separate coordinates into X and Y arrays to calculate the global combined bounding box
        x_coords = []
        y_coords = []
        for g in grid_data_list:
            pos_ft = g["position"] * self.scale
            if g["axis"] == "X":
                x_coords.append(pos_ft)
            else:
                y_coords.append(pos_ft)

        # Find coordinates of defined grids, fallback to 0.0 if an axis is empty
        x_min, x_max = (min(x_coords), max(x_coords)) if x_coords else (0.0, 0.0)
        y_min, y_max = (min(y_coords), max(y_coords)) if y_coords else (0.0, 0.0)

        # Determine standard overhang offsets (Fallback to 20m if only one grid line exists)
        x_span = x_max - x_min if len(x_coords) > 1 else (20.0 * self.scale)
        y_span = y_max - y_min if len(y_coords) > 1 else (20.0 * self.scale)
        
        # Calculate proportional overhangs (at least 15% of span, minimum of 4 meters)
        overhang_x = max(x_span * 0.15, 4.0 * self.scale)
        overhang_y = max(y_span * 0.15, 4.0 * self.scale)

        # Draw vertical lines (X-Axis) based on Y footprint or default range
        if not y_coords:
            min_grid_y = -15.0 * self.scale
            max_grid_y = 15.0 * self.scale
        else:
            min_grid_y = y_min - overhang_y
            max_grid_y = y_max + overhang_y

        # Draw horizontal lines (Y-Axis) based on X footprint or default range
        if not x_coords:
            min_grid_x = -15.0 * self.scale
            max_grid_x = 15.0 * self.scale
        else:
            min_grid_x = x_min - overhang_x
            max_grid_x = x_max + overhang_x

        compiled_grids = []
        
        for g in grid_data_list:
            pos_ft = g["position"] * self.scale
            if g["axis"] == "X":
                compiled_grids.append(GridModel(
                    id=g["id"],
                    name=g["name"],
                    start=Point2D(pos_ft, min_grid_y),
                    end=Point2D(pos_ft, max_grid_y),
                    is_pinned=True
                ))
            else:
                compiled_grids.append(GridModel(
                    id=g["id"],
                    name=g["name"],
                    start=Point2D(min_grid_x, pos_ft),
                    end=Point2D(max_grid_x, pos_ft),
                    is_pinned=True
                ))

        return compiled_grids
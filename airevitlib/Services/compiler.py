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

    def __init__(self, raw_ai_response: dict):
        self.ai_data = raw_ai_response
        self.delta = raw_ai_response.get("proposed_delta", {})
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
        # Extract all proposed grid coordinates
        x_grids = []
        y_grids = []
        
        grid_data_list = (
            self.delta.get("grids", {}).get("create", []) + 
            self.delta.get("grids", {}).get("update", [])
        )

        for g in grid_data_list:
            pos_ft = float(g["position"]) * self.scale
            if g["axis"].upper() == "X":
                x_grids.append((g, pos_ft))
            else:
                y_grids.append((g, pos_ft))

        # If there are no grids on either axis, return empty immediately
        if not x_grids and not y_grids:
            return []

        # Find coordinates of defined grids, fallback to 0.0 if an axis is empty
        x_coords = [pos for _, pos in x_grids] if x_grids else [0.0]
        y_coords = [pos for _, pos in y_grids] if y_grids else [0.0]
        
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        # Determine standard overhang offsets (Fallback to 20m if only one grid line exists)
        x_span = x_max - x_min if len(x_grids) > 1 else (20.0 * self.scale)
        y_span = y_max - y_min if len(y_grids) > 1 else (20.0 * self.scale)
        
        overhang_x = max(x_span * 0.10, 5.0)
        overhang_y = max(y_span * 0.10, 5.0)

        # Draw vertical lines (X-Axis) based on Y footprint or default range
        if not y_grids:
            min_grid_y = -15.0 * self.scale
            max_grid_y = 15.0 * self.scale
        else:
            min_grid_y = y_min - overhang_y
            max_grid_y = y_max + overhang_y

        # Draw horizontal lines (Y-Axis) based on X footprint or default range
        if not x_grids:
            min_grid_x = -15.0 * self.scale
            max_grid_x = 15.0 * self.scale
        else:
            min_grid_x = x_min - overhang_x
            max_grid_x = x_max + overhang_x

        compiled_grids = []
        
        for g, x_pos in x_grids:
            compiled_grids.append(GridModel(
                id=g["id"],
                name=g["name"],
                start=Point2D(x_pos, min_grid_y),
                end=Point2D(x_pos, max_grid_y),
                is_pinned=True
            ))

        for g, y_pos in y_grids:
            compiled_grids.append(GridModel(
                id=g["id"],
                name=g["name"],
                start=Point2D(min_grid_x, y_pos),
                end=Point2D(max_grid_x, y_pos),
                is_pinned=True
            ))

        return compiled_grids
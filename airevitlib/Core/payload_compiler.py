# lib/payload_compiler.py
from typing import Dict, Any

class PayloadCompiler:
    """Compiles programmatic structural intent into precise coordinate-based pyRevit payloads."""

    def __init__(self, intent_data: Dict[str, Any], grid_offset_buffer: float = 4000.0):
        self.intent = intent_data
        self.buffer = grid_offset_buffer
        self.unit = self.intent.get("units", "mm").lower()

    def compile(self) -> Dict[str, Any]:
        """Runs compilation math and outputs the validated coordinate payload."""
        levels = self._compile_levels()
        grids = self._compile_grids()

        return {
            "settings": {
                "grids_unit": self.unit,
                "levels_unit": self.unit,
                "coordinate_system": self.intent.get("coordinate_system", "project_base_point")
            },
            "level_strategy": {
                "mode": "explicit",
                "link_name": None,
                "prefix_copied_levels": ""
            },
            "grid_strategy": {
                "mode": "explicit",
                "link_name": None,
                "prefix_copied_grids": ""
            },
            "levels": levels,
            "grids": grids
        }

    def _compile_levels(self) -> list:
        compiled_levels = []
        for lvl in self.intent.get("levels", []):
            slug = lvl["name"].lower().replace(" ", "_").replace("-", "")
            lvl_id = f"lvl_{slug}"

            compiled_levels.append({
                "id": lvl_id,
                "name": lvl["name"],
                "elevation": float(lvl.get("elevation", 0.0)),
                "is_pinned": True,
                "create_floor_plan": lvl.get("create_floor_plan", True)
            })
        return compiled_levels

    def _compile_grids(self) -> list:
        compiled_grids = []
        x_bays = self.intent.get("grids", {}).get("x_axis", {}).get("bays", [])
        y_bays = self.intent.get("grids", {}).get("y_axis", {}).get("bays", [])

        # Calculate absolute positions along the axes
        x_positions = []
        current_x = 0.0
        for bay in x_bays:
            x_positions.append((bay["label"], current_x))
            current_x += bay.get("spacing_to_next", 0.0)

        y_positions = []
        current_y = 0.0
        for bay in y_bays:
            y_positions.append((bay["label"], current_y))
            current_y += bay.get("spacing_to_next", 0.0)

        if not x_positions or not y_positions:
            return []

        # Find absolute extents of our grid system
        max_x = x_positions[-1][1]
        max_y = y_positions[-1][1]

        # Define grid boundary coordinates including our offset cushion
        min_grid_y = 0.0 - self.buffer
        max_grid_y = max_y + self.buffer

        min_grid_x = 0.0 - self.buffer
        max_grid_x = max_x + self.buffer

        # X-Axis Grids
        for label, x_val in x_positions:
            grid_id = f"g_x_{label.lower()}"
            compiled_grids.append({
                "id": grid_id,
                "name": label,
                "start": {"x": float(x_val), "y": float(min_grid_y)},
                "end": {"x": float(x_val), "y": float(max_grid_y)},
                "is_pinned": True
            })

        # Y-Axis Grids
        for label, y_val in y_positions:
            grid_id = f"g_y_{label.lower()}"
            compiled_grids.append({
                "id": grid_id,
                "name": label,
                "start": {"x": float(min_grid_x), "y": float(y_val)},
                "end": {"x": float(max_grid_x), "y": float(y_val)},
                "is_pinned": True
            })

        return compiled_grids
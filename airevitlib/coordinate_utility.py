# airevitlib/revit/coordinate_utility.py
import math
import Autodesk.Revit.DB as DB

class CoordinateUtility:
    """Calculates coordinate transformations for structural grid and level setups."""
    
    def __init__(self, doc: DB.Document, system_type: str):
        self.doc = doc
        self.system_type = system_type.lower()
        self.translation, self.rotation_angle = self._get_coordinate_system_data()

    def _get_coordinate_system_data(self):
        translation = DB.XYZ.Zero
        rotation = 0.0  # Force orthogonal project rotation (Project North)

        if self.system_type == "internal_origin":
            return translation, rotation

        category = DB.BuiltInCategory.OST_ProjectBasePoint
        if self.system_type == "survey_point":
            category = DB.BuiltInCategory.OST_SharedBasePoint

        base_point = DB.FilteredElementCollector(self.doc) \
            .OfCategory(category) \
            .WhereElementIsNotElementType() \
            .FirstElement()

        if base_point:
            # Extract the exact parameters of the base points
            ew = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM).AsDouble()
            ns = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM).AsDouble()
            elev = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM).AsDouble()
            translation = DB.XYZ(ew, ns, elev)
            
            # NOTE: True North rotation is intentionally kept at 0.0 in the database.
            # This ensures grids remain perpendicular (Project North) for standard modeling,
            # allowing Revit's view-level Orientation property to handle geographic rotation.

        return translation, rotation

    def transform_point(self, x: float, y: float, z: float = 0.0, is_level: bool = False) -> DB.XYZ:
        """Applies manual coordinate translations. Keeps grids and levels perpendicular."""
        if is_level:
            # Levels in Revit are always absolute to the Internal Origin Z-axis.
            # Shifting level elements geographically breaks linked file coordination.
            return DB.XYZ(0.0, 0.0, z)

        cos_a = math.cos(self.rotation_angle)
        sin_a = math.sin(self.rotation_angle)
        
        # 1. Rotate coordinates (will be perfectly orthogonal since rotation_angle is 0.0)
        rotated_x = x * cos_a - y * sin_a
        rotated_y = x * sin_a + y * cos_a

        # 2. Translate coordinates relative to base point
        final_x = rotated_x + self.translation.X
        final_y = rotated_y + self.translation.Y
        final_z = z + self.translation.Z

        return DB.XYZ(final_x, final_y, final_z)
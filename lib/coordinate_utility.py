# coordinate_utility.py
import math
import Autodesk.Revit.DB as DB

class CoordinateUtility:
    """Calculates pure Python 2D/3D coordinate transformations."""
    
    def __init__(self, doc: DB.Document, system_type: str):
        self.doc = doc
        self.system_type = system_type.lower()
        self.translation, self.rotation_angle = self._get_coordinate_system_data()

    def _get_coordinate_system_data(self):
        """Extracts translation translation point and conditional rotation angle."""
        translation = DB.XYZ.Zero
        rotation = 0.0  # Default to zero rotation (Project North)

        if self.system_type == "internal_origin":
            return translation, rotation

        # Fetch Project Base Point or Survey Point
        category = DB.BuiltInCategory.OST_ProjectBasePoint
        if self.system_type == "survey_point":
            category = DB.BuiltInCategory.OST_SharedBasePoint

        base_point = DB.FilteredElementCollector(self.doc) \
            .OfCategory(category) \
            .WhereElementIsNotElementType() \
            .FirstElement()

        if base_point:
            bbox = base_point.get_BoundingBox(None)
            if bbox:
                translation = (bbox.Min + bbox.Max) * 0.5
            
            # ONLY apply True North rotation if aligning to the geographical Survey Point.
            # Project Base Point grids align to Project North (0.0 rotation).
            if self.system_type == "survey_point":
                project_location = self.doc.ActiveProjectLocation
                if project_location:
                    project_pos = project_location.GetProjectPosition(DB.XYZ.Zero)
                    if project_pos:
                        rotation = project_pos.Angle

        return translation, rotation

    def transform_point(self, x: float, y: float, z: float = 0.0) -> DB.XYZ:
        """Applies manual 2D rotation and 3D translation offset."""
        cos_a = math.cos(self.rotation_angle)
        sin_a = math.sin(self.rotation_angle)
        
        # 1. Rotate coordinates
        rotated_x = x * cos_a - y * sin_a
        rotated_y = x * sin_a + y * cos_a

        # 2. Translate coordinates relative to origin base point
        final_x = rotated_x + self.translation.X
        final_y = rotated_y + self.translation.Y
        final_z = z + self.translation.Z

        return DB.XYZ(final_x, final_y, final_z)
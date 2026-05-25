# airevitlib/revit/coordinates.py
import Autodesk.Revit.DB as DB


class CoordinateUtility:
    """Calculates precise translations relative to the Project Base Point or Survey Point."""
    
    def __init__(self, doc: DB.Document, system_type: str):
        self.doc = doc
        self.system_type = system_type.lower()
        self.translation, self.rotation_angle = self._get_coordinate_system_data()

    def _get_coordinate_system_data(self):
        translation = DB.XYZ.Zero
        rotation = 0.0

        if self.system_type == "internal_origin":
            return translation, rotation

        # Query the correct base point element category
        category = DB.BuiltInCategory.OST_ProjectBasePoint
        if self.system_type == "survey_point":
            category = DB.BuiltInCategory.OST_SharedBasePoint

        base_point = DB.FilteredElementCollector(self.doc) \
            .OfCategory(category) \
            .WhereElementIsNotElementType() \
            .FirstElement()

        if base_point:
            # Use the actual Position property of the BasePoint for coordinate stability
            if hasattr(base_point, "Position"):
                translation = base_point.Position
            else:
                # Fallback to parameter lookup if Position is not exposed
                ew = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM).AsDouble()
                ns = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM).AsDouble()
                elev = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM).AsDouble()
                translation = DB.XYZ(ew, ns, elev)

        return translation, rotation

    def transform_point(self, x: float, y: float, z: float = 0.0, is_level: bool = False) -> DB.XYZ:
        """Translates coordinates consistently so both levels and grids align perfectly at the base point."""
        if is_level:
            # Translate level height by the Base Point's vertical offset
            return DB.XYZ(0.0, 0.0, z + self.translation.Z)
        
        # Translate grids horizontally and vertically relative to the Base Point.
        return DB.XYZ(x + self.translation.X, y + self.translation.Y, z + self.translation.Z)
from pyrevit import revit, DB

class Grid(object):
    """
    Represents a Grid in Revit. 
    Handles coordinate conversions and PBP translation automatically.
    """

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        
        # When initialized, try to find an existing grid with this name
        self.revit_element = self._find_existing_grid()

    @property
    def exists(self):
        """Returns True if the grid already exists in the Revit model."""
        return self.revit_element is not None

    # ==========================================
    # CREATION METHODS
    # ==========================================

    def create_straight(self, start_pt, end_pt, unit="mm", measure_from="PBP"):
        """Creates a straight grid line in Revit using explicit start and end points."""
        if self.exists:
            print("Grid '{}' already exists. Skipping creation.".format(self.name))
            return False

        start_xyz = self._translate_coordinates(start_pt, unit, measure_from)
        end_xyz = self._translate_coordinates(end_pt, unit, measure_from)
        
        line_curve = DB.Line.CreateBound(start_xyz, end_xyz)
        return self._commit_to_revit(line_curve)

    def create_by_length(self, start_pt, direction, length, unit="mm", measure_from="PBP"):
        """Creates a straight grid by specifying a start point, a direction ('X' or 'Y'), and a total span length."""
        x, y, z = start_pt
        
        if direction.upper() == "X":
            end_pt = (x + length, y, z)
        elif direction.upper() == "Y":
            end_pt = (x, y + length, z)
        else:
            raise ValueError("Direction must be 'X' or 'Y'")
            
        return self.create_straight(start_pt, end_pt, unit, measure_from)

    def create_by_offset(self, ref_grid, vector, unit="mm"):
        """Creates a new grid by copying an existing grid and moving it by a specific distance (vector)."""
        if self.exists:
            print("Grid '{}' already exists. Skipping creation.".format(self.name))
            return False
            
        if not ref_grid.exists:
            print("Error: Cannot offset. Reference grid '{}' does not exist yet.".format(ref_grid.name))
            return False

        original_curve = ref_grid.revit_element.Curve
        
        vx, vy, vz = vector
        if unit.lower() == "mm":
            vx, vy, vz = vx / 304.8, vy / 304.8, vz / 304.8
        elif unit.lower() == "m":
            vx, vy, vz = vx / 0.3048, vy / 0.3048, vz / 0.3048
            
        translation_vector = DB.XYZ(vx, vy, vz)
        transform = DB.Transform.CreateTranslation(translation_vector)
        new_curve = original_curve.CreateTransformed(transform)
        
        return self._commit_to_revit(new_curve)

    def create_arc(self, start_pt, end_pt, center_pt, unit="mm", measure_from="PBP"):
        """Creates a curved grid in Revit."""
        if self.exists:
            print("Grid '{}' already exists. Skipping creation.".format(self.name))
            return False

        start_xyz = self._translate_coordinates(start_pt, unit, measure_from)
        end_xyz = self._translate_coordinates(end_pt, unit, measure_from)
        center_xyz = self._translate_coordinates(center_pt, unit, measure_from)
        
        arc_curve = DB.Arc.Create(start_xyz, end_xyz, center_xyz)
        return self._commit_to_revit(arc_curve)

    # ==========================================
    # MODIFICATION METHODS
    # ==========================================

    def delete(self):
        if not self.exists: return False
        with revit.Transaction("Delete Grid {}".format(self.name)):
            self.doc.Delete(self.revit_element.Id)
            self.revit_element = None
        return True

    def rename(self, new_name):
        if not self.exists: return False
        with revit.Transaction("Rename Grid {} to {}".format(self.name, new_name)):
            self.revit_element.Name = new_name
            self.name = new_name
        return True

    # ==========================================
    # PRIVATE HELPER METHODS
    # ==========================================
    
    def _find_existing_grid(self):
        all_grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).ToElements()
        for grid in all_grids:
            if grid.Name == self.name: return grid
        return None

    def _get_pbp_offset(self):
        """Finds the Project Base Point and returns its location using its BoundingBox."""
        pbp = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint).FirstElement()
        
        if pbp:
            # Safest way to get the exact XYZ of the PBP in the internal coordinate system
            bbox = pbp.get_BoundingBox(None)
            if bbox:
                return bbox.Min
                
        # Fallback if no PBP is found
        return DB.XYZ(0, 0, 0)

    def _translate_coordinates(self, coords, unit, measure_from):
        x, y, z = coords
        if unit.lower() == "mm": x, y, z = x / 304.8, y / 304.8, z / 304.8
        elif unit.lower() == "m": x, y, z = x / 0.3048, y / 0.3048, z / 0.3048
        
        if measure_from.upper() == "PBP":
            pbp_offset = self._get_pbp_offset()
            x += pbp_offset.X
            y += pbp_offset.Y
            z += pbp_offset.Z
            
        return DB.XYZ(x, y, z)

    def _commit_to_revit(self, curve):
        with revit.Transaction("Create Grid {}".format(self.name)):
            try:
                self.revit_element = DB.Grid.Create(self.doc, curve)
                self.revit_element.Name = self.name
                return True
            except Exception as e:
                print("Failed to create grid '{}'. Error: {}".format(self.name, e))
                return False
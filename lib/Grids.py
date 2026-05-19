import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB

class Grid(object):
    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.revit_element = self._find_existing_grid()

    @property
    def exists(self):
        return self.revit_element is not None

    # ==========================================
    # 1. COPY SCENARIOS (Copy/Monitor style)
    # ==========================================
    @classmethod
    def copy_all_from_link(cls, doc, link_instance):
        link_doc = link_instance.GetLinkDocument()
        if not link_doc:
            return []

        arch_grids = DB.FilteredElementCollector(link_doc).OfClass(DB.Grid).ToElements()
        transform = link_instance.GetTotalTransform()
        
        generated_grids = []
        
        # FIX: Track existing names in a Python Set before the transaction starts
        existing_grids = DB.FilteredElementCollector(doc).OfClass(DB.Grid).ToElements()
        existing_names = set([g.Name for g in existing_grids])
        
        t = DB.Transaction(doc, "Copy All Grids from Link")
        t.Start()
        try:
            for ag in arch_grids:
                # If name is already taken, skip to prevent crash
                if ag.Name in existing_names:
                    continue
                
                # Check if it's a valid curve (avoids MultiSegmentGrid crashes)
                if not hasattr(ag, "Curve") or ag.Curve is None:
                    continue
                
                new_curve = ag.Curve.CreateTransformed(transform)
                new_revit_grid = DB.Grid.Create(doc, new_curve)
                
                # FIX: Only rename if Revit didn't automatically guess the right name
                if new_revit_grid.Name != ag.Name:
                    try:
                        new_revit_grid.Name = ag.Name
                    except Exception as name_err:
                        print("Warning: Could not name grid '{}'. Revit auto-named it '{}'.".format(ag.Name, new_revit_grid.Name))
                
                # Add to our tracker so we don't duplicate it in the next loop iteration
                existing_names.add(new_revit_grid.Name)
                
                grid_obj = cls(doc, new_revit_grid.Name)
                grid_obj.revit_element = new_revit_grid
                generated_grids.append(grid_obj)
                
            t.Commit()
        except Exception as e:
            t.RollBack()
            print("Failed to copy grids: {}".format(e))
            
        return generated_grids

    # ==========================================
    # 2. DRAFTING SCENARIOS (Anchor + Offset)
    # ==========================================
    def create_anchor(self, direction, placement_coord, span_reference="Auto", padding=2000, unit="mm", measure_from="PBP"):
        if self.exists: return False

        min_span, max_span = self._resolve_span(span_reference, direction)

        coord_int = placement_coord
        pad_int = padding
        if unit.lower() == "mm":
            coord_int /= 304.8
            pad_int /= 304.8
            if isinstance(span_reference, tuple):
                min_span /= 304.8
                max_span /= 304.8
        elif unit.lower() == "m":
            coord_int /= 0.3048
            pad_int /= 0.3048
            if isinstance(span_reference, tuple):
                min_span /= 0.3048
                max_span /= 0.3048

        pbp_offset = self._get_pbp_offset() if measure_from.upper() == "PBP" else DB.XYZ(0,0,0)
        z = pbp_offset.Z
        
        if direction.upper() == "X":
            y = coord_int + pbp_offset.Y
            start_x = (min_span + pbp_offset.X) - pad_int
            end_x   = (max_span + pbp_offset.X) + pad_int
            curve = DB.Line.CreateBound(DB.XYZ(start_x, y, z), DB.XYZ(end_x, y, z))
            
        elif direction.upper() == "Y":
            x = coord_int + pbp_offset.X
            start_y = (min_span + pbp_offset.Y) - pad_int
            end_y   = (max_span + pbp_offset.Y) + pad_int
            curve = DB.Line.CreateBound(DB.XYZ(x, start_y, z), DB.XYZ(x, end_y, z))
        else:
            raise ValueError("Direction must be 'X' or 'Y'")

        return self._commit_to_revit(curve)

    def create_by_offset(self, ref_grid, vector, unit="mm"):
        if self.exists or not ref_grid.exists: return False
        vx, vy, vz = vector
        if unit.lower() == "mm": vx, vy, vz = vx / 304.8, vy / 304.8, vz / 304.8
        elif unit.lower() == "m": vx, vy, vz = vx / 0.3048, vy / 0.3048, vz / 0.3048
            
        transform = DB.Transform.CreateTranslation(DB.XYZ(vx, vy, vz))
        new_curve = ref_grid.revit_element.Curve.CreateTransformed(transform)
        return self._commit_to_revit(new_curve)

    def pin(self):
        if not self.exists or self.revit_element.Pinned: return False
        t = DB.Transaction(self.doc, "Pin Grid {}".format(self.name))
        t.Start()
        self.revit_element.Pinned = True
        t.Commit()
        return True

    # ==========================================
    # PRIVATE HELPERS
    # ==========================================
    def _resolve_span(self, span_ref, direction):
        if isinstance(span_ref, tuple): return span_ref[0], span_ref[1]

        min_pt, max_pt = None, None
        
        if hasattr(span_ref, "GetTotalTransform"): 
            bbox = span_ref.get_BoundingBox(None)
            if bbox: min_pt, max_pt = bbox.Min, bbox.Max
            
        elif span_ref == "Auto":
            links = DB.FilteredElementCollector(self.doc).OfClass(DB.RevitLinkInstance).ToElements()
            if links:
                min_x, min_y = float('inf'), float('inf')
                max_x, max_y = float('-inf'), float('-inf')
                for link in links:
                    bbox = link.get_BoundingBox(None)
                    if bbox:
                        min_x, min_y = min(min_x, bbox.Min.X), min(min_y, bbox.Min.Y)
                        max_x, max_y = max(max_x, bbox.Max.X), max(max_y, bbox.Max.Y)
                if min_x != float('inf'):
                    min_pt, max_pt = DB.XYZ(min_x, min_y, 0), DB.XYZ(max_x, max_y, 0)
            
            if not min_pt: 
                levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
                if levels:
                    min_x, min_y = float('inf'), float('inf')
                    max_x, max_y = float('-inf'), float('-inf')
                    for lvl in levels:
                        bbox = lvl.get_BoundingBox(None)
                        if bbox:
                            min_x, min_y = min(min_x, bbox.Min.X), min(min_y, bbox.Min.Y)
                            max_x, max_y = max(max_x, bbox.Max.X), max(max_y, bbox.Max.Y)
                    if min_x != float('inf'):
                        min_pt, max_pt = DB.XYZ(min_x, min_y, 0), DB.XYZ(max_x, max_y, 0)

        if min_pt and max_pt:
            if direction.upper() == "X": return min_pt.X, max_pt.X
            if direction.upper() == "Y": return min_pt.Y, max_pt.Y
            
        fallback = 50000 / 304.8
        return -fallback, fallback

    def _get_pbp_offset(self):
        pbp = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint).FirstElement()
        if pbp and pbp.get_BoundingBox(None): return pbp.get_BoundingBox(None).Min
        return DB.XYZ(0, 0, 0)

    def _find_existing_grid(self):
        all_grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).ToElements()
        for grid in all_grids:
            if grid.Name == self.name: return grid
        return None

    def _commit_to_revit(self, curve):
        t = DB.Transaction(self.doc, "Create Grid {}".format(self.name))
        t.Start()
        try:
            self.revit_element = DB.Grid.Create(self.doc, curve)
            # FIX: Check name safely
            if self.revit_element.Name != self.name:
                self.revit_element.Name = self.name
            t.Commit()
            return True
        except Exception as e:
            t.RollBack()
            print("Failed to create grid '{}'. Error: {}".format(self.name, e))
            return False
import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB

class SimpleTransaction(object):
    """A safe context manager for Revit Transactions bypassing pyRevit's wrapper."""
    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.t = DB.Transaction(self.doc, self.name)
        
    def __enter__(self):
        self.t.Start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.t.RollBack()
        else:
            self.t.Commit()

class Level(object):
    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.revit_element = self._find_existing_level()

    @property
    def exists(self):
        return self.revit_element is not None

    @property
    def elevation(self):
        if self.exists: return self.revit_element.Elevation
        return None

    @property
    def is_pinned(self):
        """Returns True if the level is pinned in Revit."""
        if self.exists: return self.revit_element.Pinned
        return False

    # ==========================================
    # CREATION METHODS
    # ==========================================

    def create_at_elevation(self, elevation, unit="mm", measure_from="PBP"):
        if self.exists: return False
        elev_internal = self._translate_elevation(elevation, unit, measure_from)
        return self._commit_to_revit(elev_internal)

    def create_by_offset(self, ref_level, z_offset, unit="mm"):
        if self.exists or not ref_level.exists: return False
        if unit.lower() == "mm": offset_internal = z_offset / 304.8
        elif unit.lower() == "m": offset_internal = z_offset / 0.3048
        else: offset_internal = z_offset

        new_elevation = ref_level.elevation + offset_internal
        return self._commit_to_revit(new_elevation)

    def create_from_link(self, link_instance, source_level_name=None):
        if self.exists: return False
        search_name = source_level_name if source_level_name else self.name
        
        link_doc = link_instance.GetLinkDocument()
        if not link_doc: return False
            
        link_levels = DB.FilteredElementCollector(link_doc).OfClass(DB.Level).ToElements()
        target_link_level = next((lvl for lvl in link_levels if lvl.Name == search_name), None)
        
        if not target_link_level: return False
            
        link_transform = link_instance.GetTotalTransform()
        link_pt = DB.XYZ(0, 0, target_link_level.Elevation)
        host_pt = link_transform.OfPoint(link_pt)
        
        return self._commit_to_revit(host_pt.Z)

    # ==========================================
    # MODIFICATION & PINNING METHODS
    # ==========================================

    def pin(self):
        """Pins the level in place (Highly recommended for draftsmen)."""
        if not self.exists or self.is_pinned: return False
        with SimpleTransaction(self.doc, "Pin Level {}".format(self.name)):
            self.revit_element.Pinned = True
        return True

    def unpin(self):
        """Unpins the level."""
        if not self.exists or not self.is_pinned: return False
        with SimpleTransaction(self.doc, "Unpin Level {}".format(self.name)):
            self.revit_element.Pinned = False
        return True

    def delete(self):
        """Deletes the level, bypassing pins automatically."""
        if not self.exists: return False
        
        # Save name BEFORE deletion to avoid crash in print statements
        deleted_name = self.revit_element.Name
        
        with SimpleTransaction(self.doc, "Delete Level {}".format(self.name)):
            if self.revit_element.Pinned:
                self.revit_element.Pinned = False
            self.doc.Delete(self.revit_element.Id)
            self.revit_element = None
            
        return True

    def rename(self, new_name):
        if not self.exists: return False
        with SimpleTransaction(self.doc, "Rename Level {} to {}".format(self.name, new_name)):
            self.revit_element.Name = new_name
            self.name = new_name
        return True

    # ==========================================
    # VIEW GENERATION
    # ==========================================

    def create_floor_plan(self):
        if not self.exists: return False
        vft = self._get_view_family_type(DB.ViewFamily.FloorPlan)
        if not vft: return False

        with SimpleTransaction(self.doc, "Create Floor Plan for {}".format(self.name)):
            view = DB.ViewPlan.Create(self.doc, vft.Id, self.revit_element.Id)
            view.Name = self.name
            return True

    def create_ceiling_plan(self):
        if not self.exists: return False
        vft = self._get_view_family_type(DB.ViewFamily.CeilingPlan)
        if not vft: return False

        with SimpleTransaction(self.doc, "Create Ceiling Plan for {}".format(self.name)):
            view = DB.ViewPlan.Create(self.doc, vft.Id, self.revit_element.Id)
            view.Name = self.name + " - RCP"
            return True

    # ==========================================
    # PRIVATE HELPER METHODS
    # ==========================================

    def _find_existing_level(self):
        all_levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements()
        for lvl in all_levels:
            if lvl.Name == self.name: return lvl
        return None

    def _get_pbp_z_offset(self):
        pbp = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint).FirstElement()
        if pbp:
            bbox = pbp.get_BoundingBox(None)
            if bbox: return bbox.Min.Z
        return 0.0

    def _translate_elevation(self, elevation, unit, measure_from):
        elev_internal = elevation
        if unit.lower() == "mm": elev_internal = elevation / 304.8
        elif unit.lower() == "m": elev_internal = elevation / 0.3048
        if measure_from.upper() == "PBP": elev_internal += self._get_pbp_z_offset()
        return elev_internal

    def _commit_to_revit(self, elevation_internal):
        # FIX: The try/except is moved OUTSIDE the SimpleTransaction 
        # so exceptions actually trigger the RollBack() inside __exit__
        try:
            with SimpleTransaction(self.doc, "Create Level {}".format(self.name)):
                self.revit_element = DB.Level.Create(self.doc, elevation_internal)
                self.revit_element.Name = self.name
            return True
        except Exception as e:
            print("Failed to create level. Error: {}".format(e))
            return False

    def _get_view_family_type(self, view_family_enum):
        vfts = DB.FilteredElementCollector(self.doc).OfClass(DB.ViewFamilyType).ToElements()
        for vft in vfts:
            if vft.ViewFamily == view_family_enum: return vft
        return None
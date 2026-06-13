# -*- coding: utf-8 -*-
"""Autodesk Revit Level tool database and boundary operations."""

class LevelTools(object):
    """Encapsulates database query and modification operations for Revit Levels."""
    
    def __init__(self, doc):
        """Initializes the LevelTools controller.
        
        Args:
            doc (Autodesk.Revit.DB.Document): The active Revit document.
        """
        self.doc = doc

    @staticmethod
    def clip_line_to_bbox_2d(p_x, p_y, d_x, d_y, min_x, min_y, max_x, max_y):
        """Clips a 2D line defined by point P and direction D inside a 2D bounding box."""
        # Parallel to Y-axis: horizontal axis in this view is Y. Only clip Y.
        if abs(d_x) < 1e-9:
            if abs(d_y) < 1e-9:
                return None
            t1 = (min_y - p_y) / d_y
            t2 = (max_y - p_y) / d_y
            return min(t1, t2), max(t1, t2)
            
        # Parallel to X-axis: horizontal axis in this view is X. Only clip X.
        if abs(d_y) < 1e-9:
            t1 = (min_x - p_x) / d_x
            t2 = (max_x - p_x) / d_x
            return min(t1, t2), max(t1, t2)
            
        # Diagonal view: standard 2D clipping against both boundaries
        t_min = float('-inf')
        t_max = float('inf')
        
        t1 = (min_x - p_x) / d_x
        t2 = (max_x - p_x) / d_x
        t_min = max(t_min, min(t1, t2))
        t_max = min(t_max, max(t1, t2))
        
        t1 = (min_y - p_y) / d_y
        t2 = (max_y - p_y) / d_y
        t_min = max(t_min, min(t1, t2))
        t_max = min(t_max, max(t1, t2))
        
        if t_min > t_max:
            return None
            
        return t_min, t_max

    @staticmethod
    def apply_level_extents_to_views(doc, level, min_x, min_y, max_x, max_y):
        """Updates level extents inside all Elevation and Section views to match horizontal coordinates."""
        from Autodesk.Revit.DB import FilteredElementCollector, ViewSection, XYZ, Line, DatumExtentType
        
        views = FilteredElementCollector(doc).OfClass(ViewSection).ToElements()
        
        x0, x1 = min(min_x, max_x), max(min_x, max_x)
        y0, y1 = min(min_y, max_y), max(min_y, max_y)
        elevation = level.Elevation
        
        for v in views:
            if v.IsTemplate:
                continue
            if not level.CanBeVisibleInView(v):
                continue
                
            n = v.ViewDirection
            origin = v.Origin
            
            # Calculate coordinate on the projection plane
            denom_y = abs(n.Y)
            denom_x = abs(n.X)
            
            if denom_y > 1e-9:
                p_x = origin.X
                p_y = origin.Y - n.Z * (elevation - origin.Z) / n.Y
            elif denom_x > 1e-9:
                p_x = origin.X - n.Z * (elevation - origin.Z) / n.X
                p_y = origin.Y
            else:
                continue
                
            p = XYZ(p_x, p_y, elevation)
            
            # Determine the horizontal direction vector of the Level line in this view
            z_axis = XYZ(0, 0, 1)
            d = n.CrossProduct(z_axis).Normalize()
            
            clip_res = LevelTools.clip_line_to_bbox_2d(p.X, p.Y, d.X, d.Y, x0, y0, x1, y1)
            if not clip_res:
                continue
                
            t_min, t_max = clip_res
            pt_start = p + d * t_min
            pt_end = p + d * t_max
            
            try:
                new_curve = Line.CreateBound(pt_start, pt_end)
                for extent_type in [DatumExtentType.Model, DatumExtentType.ViewSpecific]:
                    try:
                        level.SetCurveInView(extent_type, v, new_curve)
                    except Exception:
                        pass
            except Exception:
                pass

    @staticmethod
    def copy_level_extents(doc, ref_level, target_level):
        """Copies both Model and View-specific extents from a reference level to target level."""
        from Autodesk.Revit.DB import FilteredElementCollector, ViewSection, XYZ, Transform, DatumExtentType
        
        views = FilteredElementCollector(doc).OfClass(ViewSection).ToElements()
        elevation_diff = target_level.Elevation - ref_level.Elevation
        translation_vector = XYZ(0, 0, elevation_diff)
        translation_transform = Transform.CreateTranslation(translation_vector)
        
        for v in views:
            if v.IsTemplate:
                continue
            if ref_level.CanBeVisibleInView(v) and target_level.CanBeVisibleInView(v):
                for extent_type in [DatumExtentType.Model, DatumExtentType.ViewSpecific]:
                    try:
                        ref_curves = ref_level.GetCurvesInView(extent_type, v)
                        if ref_curves:
                            ref_curve = ref_curves[0]
                            target_curve = ref_curve.CreateTransformed(translation_transform)
                            target_level.SetCurveInView(extent_type, v, target_curve)
                    except Exception:
                        pass

    def fetch_all(self):
        """Queries and formats all levels inside the active Revit document with visual boundaries."""
        from Autodesk.Revit.DB import FilteredElementCollector, Level, BuiltInCategory
        from collections import OrderedDict

        # Calculate the actual physical building envelope/extents
        envelope_categories = [
            BuiltInCategory.OST_Walls,
            BuiltInCategory.OST_Floors,
            BuiltInCategory.OST_Roofs,
            BuiltInCategory.OST_StructuralColumns,
            BuiltInCategory.OST_StructuralFraming,
            BuiltInCategory.OST_StructuralFoundation,
            BuiltInCategory.OST_GenericModel,
            BuiltInCategory.OST_Grids
        ]
        
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        has_geometry = False
        
        # Union the bounding boxes of all envelope-defining elements
        for cat in envelope_categories:
            try:
                elements = FilteredElementCollector(self.doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()
                for el in elements:
                    bbox = el.get_BoundingBox(None)
                    if bbox:
                        pt0 = bbox.Min
                        pt1 = bbox.Max
                        
                        if pt0.X < min_x: min_x = pt0.X
                        if pt0.Y < min_y: min_y = pt0.Y
                        if pt1.X > max_x: max_x = pt1.X
                        if pt1.Y > max_y: max_y = pt1.Y
                        has_geometry = True
            except Exception:
                continue

        levels = FilteredElementCollector(self.doc).OfClass(Level)
        levels_data = []
        
        from Autodesk.Revit.DB import ViewSection, DatumExtentType
        views = FilteredElementCollector(self.doc).OfClass(ViewSection).ToElements()
        
        for lvl in levels:
            # Query the actual 3D model curves of the Level in all elevation/section views to find its true bounds
            lvl_min_x = lvl_min_y = float('inf')
            lvl_max_x = lvl_max_y = float('-inf')
            found_bounds = False
            
            for v in views:
                if v.IsTemplate:
                    continue
                try:
                    if not lvl.CanBeVisibleInView(v):
                        continue
                except Exception:
                    continue
                
                try:
                    # Attempt to get Model curves first, then fallback to ViewSpecific curves
                    curves = lvl.GetCurvesInView(DatumExtentType.Model, v)
                    if not curves:
                        curves = lvl.GetCurvesInView(DatumExtentType.ViewSpecific, v)
                        
                    if curves:
                        for c in curves:
                            if c.IsBound:
                                pt0 = c.GetEndPoint(0)
                                pt1 = c.GetEndPoint(1)
                                
                                lvl_min_x = min(lvl_min_x, pt0.X, pt1.X)
                                lvl_min_y = min(lvl_min_y, pt0.Y, pt1.Y)
                                lvl_max_x = max(lvl_max_x, pt0.X, pt1.X)
                                lvl_max_y = max(lvl_max_y, pt0.Y, pt1.Y)
                                found_bounds = True
                except Exception:
                    continue

            if not found_bounds:
                # Determine the unique 3D bounding box coordinates of the level if no view curves found
                lvl_bbox = lvl.get_BoundingBox(None)
                if lvl_bbox:
                    lvl_min_x = lvl_bbox.Min.X
                    lvl_min_y = lvl_bbox.Min.Y
                    lvl_max_x = lvl_bbox.Max.X
                    lvl_max_y = lvl_bbox.Max.Y
                elif has_geometry:
                    # Fallback to model footprint envelope
                    lvl_min_x = min_x
                    lvl_min_y = min_y
                    lvl_max_x = max_x
                    lvl_max_y = max_y
                else:
                    # Sane absolute fallback bounds
                    lvl_min_x = 0.0
                    lvl_min_y = 0.0
                    lvl_max_x = 100.0
                    lvl_max_y = 100.0

            start_coords = OrderedDict([
                ("x", round(lvl_min_x, 3)),
                ("y", round(lvl_min_y, 3)),
                ("z", round(lvl.Elevation, 3))
            ])
            end_coords = OrderedDict([
                ("x", round(lvl_max_x, 3)),
                ("y", round(lvl_max_y, 3)),
                ("z", round(lvl.Elevation, 3))
            ])
            
            lvl_dict = OrderedDict([
                ("name", lvl.Name),
                ("level_id", lvl.UniqueId),
                ("elevation", round(lvl.Elevation, 3)),
                ("model_extent_start", start_coords),
                ("model_extent_end", end_coords)
            ])
            
            levels_data.append(lvl_dict)
            
        return OrderedDict([
            ("status", "success"),
            ("message", "Successfully fetched levels with precise visual bounds."),
            ("measurement_unit", "feet"),
            ("data", OrderedDict([("levels", levels_data)]))
        ])

    def create(self, name, elevation, min_x=None, min_y=None, max_x=None, max_y=None, reference_level_id=None, maximize_extents=True):
        """Creates a new horizontal datum level.
        
        Args:
            name (str): Unique name of the new level.
            elevation (float): Elevation height in feet.
            min_x (float, optional): Custom minimum X visual boundary.
            min_y (float, optional): Custom minimum Y visual boundary.
            max_x (float, optional): Custom maximum X visual boundary.
            max_y (float, optional): Custom maximum Y visual boundary.
            reference_level_id (str, optional): UniqueId of level to copy extents from.
            maximize_extents (bool, optional): Option to maximize 3D extents (default True).
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Level, FilteredElementCollector
        from collections import OrderedDict

        for lvl in FilteredElementCollector(self.doc).OfClass(Level):
            if lvl.Name.lower() == name.lower():
                return {"status": "error", "message": "Level name '{}' already exists.".format(name)}

        with Transaction(self.doc, "Agent - Create Level") as trans:
            trans.Start()
            try:
                new_level = Level.Create(self.doc, elevation)
                new_level.Name = name
                
                if maximize_extents:
                    new_level.Maximize3DExtents()

                if reference_level_id:
                    ref_level = self.doc.GetElement(reference_level_id)
                    if not ref_level or not isinstance(ref_level, Level):
                        return {"status": "error", "message": "Reference level '{}' not found.".format(reference_level_id)}
                    self.copy_level_extents(self.doc, ref_level, new_level)
                else:
                    if all(v is not None for v in [min_x, min_y, max_x, max_y]):
                        self.apply_level_extents_to_views(self.doc, new_level, min_x, min_y, max_x, max_y)

                new_level.Pinned = True
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Level '{}' successfully created.".format(name)),
                    ("measurement_unit", "feet"),
                    ("data", OrderedDict([("element_id", new_level.UniqueId)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to create level: " + str(ex)}

    def modify(self, level_id, name=None, elevation=None, min_x=None, min_y=None, max_x=None, max_y=None, reference_level_id=None, maximize_extents=None):
        """Modifies height elevation, name, or extents of an existing level.
        
        Args:
            level_id (str): UniqueId of the target Level.
            name (str, optional): New name for the level.
            elevation (float, optional): New elevation height.
            min_x (float, optional): New minimum X boundary.
            min_y (float, optional): New minimum Y boundary.
            max_x (float, optional): New maximum X boundary.
            max_y (float, optional): New maximum Y boundary.
            reference_level_id (str, optional): UniqueId of level to copy extents from.
            maximize_extents (bool, optional): Option to maximize 3D extents.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Level, FilteredElementCollector
        from collections import OrderedDict

        level = self.doc.GetElement(level_id)
        if not level or not isinstance(level, Level):
            return {"status": "error", "message": "Level element not found."}

        with Transaction(self.doc, "Agent - Modify Level") as trans:
            trans.Start()
            try:
                was_pinned = level.Pinned
                level.Pinned = False

                if elevation is not None:
                    level.Elevation = float(elevation)

                if name and name != level.Name:
                    for lvl in FilteredElementCollector(self.doc).OfClass(Level):
                        if lvl.Id != level.Id and lvl.Name.lower() == name.lower():
                            return {"status": "error", "message": "Level name '{}' already exists.".format(name)}
                    level.Name = str(name)

                if maximize_extents:
                    level.Maximize3DExtents()

                if reference_level_id:
                    ref_level = self.doc.GetElement(reference_level_id)
                    if not ref_level or not isinstance(ref_level, Level):
                        return {"status": "error", "message": "Reference level '{}' not found.".format(reference_level_id)}
                    self.copy_level_extents(self.doc, ref_level, level)
                else:
                    coords = [min_x, min_y, max_x, max_y]
                    if any(v is not None for v in coords):
                        bbox = level.get_BoundingBox(None)
                        cur_min_x = bbox.Min.X if bbox else 0.0
                        cur_min_y = bbox.Min.Y if bbox else 0.0
                        cur_max_x = bbox.Max.X if bbox else 100.0
                        cur_max_y = bbox.Max.Y if bbox else 100.0
                        
                        new_min_x = float(min_x if min_x is not None else cur_min_x)
                        new_min_y = float(min_y if min_y is not None else cur_min_y)
                        new_max_x = float(max_x if max_x is not None else cur_max_x)
                        new_max_y = float(max_y if max_y is not None else cur_max_y)
                        
                        self.apply_level_extents_to_views(self.doc, level, new_min_x, new_min_y, new_max_x, new_max_y)

                level.Pinned = was_pinned
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Level '{}' successfully modified.".format(level.Name)),
                    ("measurement_unit", "feet"),
                    ("data", OrderedDict([("element_id", level.UniqueId)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to modify level: " + str(ex)}

    def delete(self, level_id, ui_app=None):
        """Deletes an existing level from the document.
        
        Args:
            level_id (str): UniqueId of the target Level.
            ui_app (Autodesk.Revit.UI.UIApplication, optional): The Revit UIApplication context.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Level, FilteredElementCollector, View, ViewType
        from collections import OrderedDict

        level = self.doc.GetElement(level_id)
        if not level or not isinstance(level, Level):
            return {"status": "error", "message": "Level element not found."}

        uidoc = ui_app.ActiveUIDocument if ui_app else None
        active_view = uidoc.ActiveView if uidoc else None

        if uidoc and active_view:
            active_view_deleted = False
            try:
                if active_view.GenLevel and active_view.GenLevel.Id == level.Id:
                    active_view_deleted = True
            except Exception:
                pass

            if active_view_deleted:
                # Find a safe view to switch to (must not be associated with the level being deleted)
                allowed_types = [
                    ViewType.FloorPlan,
                    ViewType.CeilingPlan,
                    ViewType.ThreeD,
                    ViewType.Elevation,
                    ViewType.Section,
                    ViewType.DraftingView
                ]
                
                safe_view = None
                for v in FilteredElementCollector(self.doc).OfClass(View):
                    if v.IsTemplate:
                        continue
                    
                    is_assoc = False
                    try:
                        if v.GenLevel and v.GenLevel.Id == level.Id:
                            is_assoc = True
                    except Exception:
                        pass
                    
                    if is_assoc:
                        continue
                        
                    if v.ViewType in allowed_types:
                        safe_view = v
                        break
                
                if safe_view:
                    try:
                        uidoc.ActiveView = safe_view
                    except Exception as ex:
                        return {"status": "error", "message": "Cannot delete level because it is associated with the active view, and switching views failed: " + str(ex)}
                else:
                    return {"status": "error", "message": "Cannot delete level because it is associated with the active view, and no other safe view was found to switch to."}

        with Transaction(self.doc, "Agent - Delete Level") as trans:
            trans.Start()
            try:
                level.Pinned = False
                self.doc.Delete(level.Id)
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Level and its associated views successfully deleted."),
                    ("measurement_unit", "feet")
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to delete level: " + str(ex)}

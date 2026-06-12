# -*- coding: utf-8 -*-
"""Autodesk Revit Grid tool database operations."""

class GridTools(object):
    """Encapsulates database query and modification operations for Revit Grids."""
    
    def __init__(self, doc):
        """Initializes the GridTools controller.
        
        Args:
            doc (Autodesk.Revit.DB.Document): The active Revit document.
        """
        self.doc = doc

    def fetch_all(self):
        """Queries and formats all gridlines inside the active Revit document.
        
        Returns:
            dict: Structured payload containing status, message, and list of grids.
        """
        from Autodesk.Revit.DB import FilteredElementCollector, Grid, Line, Arc
        from collections import OrderedDict
        
        grids = FilteredElementCollector(self.doc).OfClass(Grid).WhereElementIsNotElementType().ToElements()
        grids_data = []
        
        for g in grids:
            g_curve = g.Curve
            is_curved = not isinstance(g_curve, Line)
            
            start_pt = None
            end_pt = None
            center_pt = None
            radius = None
            
            if g_curve:
                if g_curve.IsBound:
                    start_pt = g_curve.GetEndPoint(0)
                    end_pt = g_curve.GetEndPoint(1)
                
                if isinstance(g_curve, Arc):
                    center_pt = g_curve.Center
                    radius = g_curve.Radius

            # Format start coordinates
            start_coords = None
            if start_pt:
                start_coords = OrderedDict([
                    ("x", round(start_pt.X, 3)),
                    ("y", round(start_pt.Y, 3)),
                    ("z", round(start_pt.Z, 3))
                ])

            # Format end coordinates
            end_coords = None
            if end_pt:
                end_coords = OrderedDict([
                    ("x", round(end_pt.X, 3)),
                    ("y", round(end_pt.Y, 3)),
                    ("z", round(end_pt.Z, 3))
                ])

            # Format arc/curved geometry parameters if applicable
            arc_details = None
            if is_curved and center_pt and radius is not None:
                arc_details = OrderedDict([
                    ("center_x", round(center_pt.X, 3)),
                    ("center_y", round(center_pt.Y, 3)),
                    ("center_z", round(center_pt.Z, 3)),
                    ("radius", round(radius, 3))
                ])
            
            grid_dict = OrderedDict([
                ("name", g.Name),
                ("grid_id", g.UniqueId),
                ("is_curved", is_curved),
                ("pinned", g.Pinned),
                ("start_coords", start_coords),
                ("end_coords", end_coords),
                ("arc_details", arc_details)
            ])
            
            grids_data.append(grid_dict)
            
        return OrderedDict([
            ("status", "success"),
            ("message", "Successfully fetched all project grids."),
            ("data", OrderedDict([("grids", grids_data)]))
        ])

    def create(self, name, start_pt, end_pt, view=None):
        """Creates a new linear grid line in the document.
        
        Args:
            name (str): Unique label for the new grid line.
            start_pt (XYZ): The starting XYZ coordinates (feet).
            end_pt (XYZ): The ending XYZ coordinates (feet).
            view (Autodesk.Revit.DB.View, optional): The active document view.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Line, Grid, FilteredElementCollector, Level
        from collections import OrderedDict

        for g in FilteredElementCollector(self.doc).OfClass(Grid):
            if g.Name.lower() == name.lower():
                return {"status": "error", "message": "Grid name '{}' already exists.".format(name)}

        # Determine vertical extents based on all document levels to ensure grid intersects them vertically
        levels = FilteredElementCollector(self.doc).OfClass(Level).WhereElementIsNotElementType().ToElements()
        if levels:
            elevations = [l.Elevation for l in levels]
            bottom = min(elevations) - 10.0
            top = max(elevations) + 10.0
        else:
            bottom = -20.0
            top = 150.0

        with Transaction(self.doc, "Agent - Create Grid") as trans:
            trans.Start()
            try:
                line = Line.CreateBound(start_pt, end_pt)
                new_grid = Grid.Create(self.doc, line)
                new_grid.Name = name
                
                # Explicitly override Revit's default automatic extent length with the exact input bounds
                if view:
                    try:
                        from Autodesk.Revit.DB import DatumExtentType, DatumEnds
                        new_grid.SetDatumExtentType(DatumEnds.End0, view, DatumExtentType.Model)
                        new_grid.SetDatumExtentType(DatumEnds.End1, view, DatumExtentType.Model)
                        new_grid.SetCurveInView(DatumExtentType.Model, view, line)
                    except Exception:
                        pass
                        
                new_grid.SetVerticalExtents(bottom, top)
                new_grid.Pinned = True
                trans.Commit()
                
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Grid '{}' successfully created.".format(name)),
                    ("data", OrderedDict([("element_id", new_grid.UniqueId)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to create grid: " + str(ex)}

    def modify(self, grid_id, name=None, start_pt=None, end_pt=None, view=None):
        """Modifies coordinates and/or renames an existing grid line.
        
        Args:
            grid_id (str): UniqueId of the target Grid.
            name (str, optional): New grid name/label.
            start_pt (XYZ, optional): New start coordinates.
            end_pt (XYZ, optional): New end coordinates.
            view (Autodesk.Revit.DB.View, optional): The active document view.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Line, Grid, FilteredElementCollector, Level
        from collections import OrderedDict

        grid = self.doc.GetElement(grid_id)
        if not grid or not isinstance(grid, Grid):
            return {"status": "error", "message": "Grid element not found."}

        # Determine vertical extents based on all document levels to ensure grid intersects them vertically
        levels = FilteredElementCollector(self.doc).OfClass(Level).WhereElementIsNotElementType().ToElements()
        if levels:
            elevations = [l.Elevation for l in levels]
            bottom = min(elevations) - 10.0
            top = max(elevations) + 10.0
        else:
            bottom = -20.0
            top = 150.0

        with Transaction(self.doc, "Agent - Modify Grid") as trans:
            trans.Start()
            try:
                final_name = name if name else grid.Name
                final_id = grid.UniqueId

                if start_pt is not None and end_pt is not None:
                    # Store original properties
                    old_name = grid.Name
                    was_pinned = grid.Pinned
                    
                    # Rename old grid to avoid name collision when creating the new grid
                    grid.Name = old_name + "_temp_" + str(grid.Id.IntegerValue)
                    
                    # Unpin and delete the old grid
                    grid.Pinned = False
                    self.doc.Delete(grid.Id)
                    
                    # Create the new grid with the updated coordinates
                    new_line = Line.CreateBound(start_pt, end_pt)
                    new_grid = Grid.Create(self.doc, new_line)
                    new_grid.Name = final_name
                    
                    # Explicitly override Revit's default automatic extent length with the exact input bounds
                    if view:
                        try:
                            from Autodesk.Revit.DB import DatumExtentType, DatumEnds
                            new_grid.SetDatumExtentType(DatumEnds.End0, view, DatumExtentType.Model)
                            new_grid.SetDatumExtentType(DatumEnds.End1, view, DatumExtentType.Model)
                            new_grid.SetCurveInView(DatumExtentType.Model, view, new_line)
                        except Exception:
                            pass
                            
                    new_grid.SetVerticalExtents(bottom, top)
                    new_grid.Pinned = was_pinned
                    final_id = new_grid.UniqueId
                else:
                    # Just rename if coordinates are not changed
                    if name and name != grid.Name:
                        grid.Name = str(name)

                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Grid '{}' successfully modified.".format(final_name)),
                    ("data", OrderedDict([("element_id", final_id)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to modify grid: " + str(ex)}

    def delete(self, grid_id):
        """Deletes an existing grid line from the document.
        
        Args:
            grid_id (str): UniqueId of the target Grid.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, Grid
        from collections import OrderedDict

        grid = self.doc.GetElement(grid_id)
        if not grid or not isinstance(grid, Grid):
            return {"status": "error", "message": "Grid element not found."}

        with Transaction(self.doc, "Agent - Delete Grid") as trans:
            trans.Start()
            try:
                grid.Pinned = False
                self.doc.Delete(grid.Id)
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Grid successfully deleted.")
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to delete grid: " + str(ex)}

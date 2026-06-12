# -*- coding: utf-8 -*-
"""Autodesk Revit Structural Column database operations and type definitions."""

class ColumnTools(object):
    """Encapsulates database query and modification operations for Revit Structural Columns."""

    def __init__(self, doc):
        """Initializes the ColumnTools controller.
        
        Args:
            doc (Autodesk.Revit.DB.Document): The active Revit document.
        """
        self.doc = doc

    def _get_default_column_symbol(self):
        """Locates the first loaded structural column family symbol in the document.
        
        Returns:
            Autodesk.Revit.DB.FamilySymbol: The family symbol, or None if none loaded.
        """
        from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol, BuiltInCategory
        
        collector = FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns)
        for symbol in collector:
            return symbol
        return None

    def _get_symbol_name(self, symbol):
        """Safely retrieves the name of a FamilySymbol, avoiding IronPython Name property bugs.
        
        Args:
            symbol (Autodesk.Revit.DB.FamilySymbol): The family symbol.
            
        Returns:
            str: The name of the symbol, or 'Unknown Type'.
        """
        if not symbol:
            return "Unknown Type"
        from Autodesk.Revit.DB import BuiltInParameter
        try:
            # 1. Try SYMBOL_NAME_PARAM
            p = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p and p.HasValue:
                val = p.AsString()
                if val:
                    return val
            # 2. Try ALL_MODEL_TYPE_NAME
            p = symbol.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
            if p and p.HasValue:
                val = p.AsString()
                if val:
                    return val
            # 3. Fallback to getattr Name
            return symbol.Name
        except Exception:
            return "Unknown Type"

    def _set_parameter_value(self, param, val):
        """Safely sets a parameter value based on its storage type.
        
        Args:
            param (Autodesk.Revit.DB.Parameter): The parameter to set.
            val: The value to write.
            
        Returns:
            bool: True if set successfully, False otherwise.
        """
        if not param or param.IsReadOnly:
            return False
            
        from Autodesk.Revit.DB import StorageType, ElementId
        try:
            if param.StorageType == StorageType.Double:
                param.Set(float(val))
            elif param.StorageType == StorageType.Integer:
                param.Set(int(float(val)))
            elif param.StorageType == StorageType.String:
                param.Set(str(val))
            elif param.StorageType == StorageType.ElementId:
                if isinstance(val, int):
                    param.Set(ElementId(val))
                else:
                    try:
                        param.Set(ElementId(int(val)))
                    except Exception:
                        el = self.doc.GetElement(str(val))
                        if el:
                            param.Set(el.Id)
            return True
        except Exception:
            return False

    def _get_level(self, level_id_or_name):
        """Helper to resolve a Level by UniqueId or Name.
        
        Args:
            level_id_or_name (str): UniqueId or Name of the Level.
            
        Returns:
            Autodesk.Revit.DB.Level: The resolved level, or None.
        """
        from Autodesk.Revit.DB import FilteredElementCollector, Level
        if not level_id_or_name:
            return None
            
        # Try finding by UniqueId
        el = self.doc.GetElement(level_id_or_name)
        if el and isinstance(el, Level):
            return el
            
        # Try finding by name
        for lvl in FilteredElementCollector(self.doc).OfClass(Level):
            if lvl.Name.lower() == level_id_or_name.lower():
                return lvl
        return None

    def _get_column_level_parameters(self, column):
        """Helper to resolve base/top levels and base/top offset parameters of a column.
        
        Args:
            column (Autodesk.Revit.DB.FamilyInstance): Column instance.
            
        Returns:
            tuple: (base_level_param, top_level_param, base_offset_param, top_offset_param)
        """
        from Autodesk.Revit.DB import BuiltInParameter
        
        # Base Level Parameter
        base_param = column.get_Parameter(BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
        if not base_param:
            base_param = column.get_Parameter(BuiltInParameter.SCHEDULE_BASE_LEVEL_PARAM)
            
        # Top Level Parameter
        top_param = column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
        if not top_param:
            top_param = column.get_Parameter(BuiltInParameter.SCHEDULE_TOP_LEVEL_PARAM)
            
        # Base Offset Parameter
        base_offset_param = column.get_Parameter(BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM)
        if not base_offset_param:
            base_offset_param = column.get_Parameter(BuiltInParameter.SCHEDULE_BASE_LEVEL_OFFSET_PARAM)
            
        # Top Offset Parameter
        top_offset_param = column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
        if not top_offset_param:
            top_offset_param = column.get_Parameter(BuiltInParameter.SCHEDULE_TOP_LEVEL_OFFSET_PARAM)
            
        return base_param, top_param, base_offset_param, top_offset_param

    def fetch_all(self):
        """Queries and formats all structural columns inside the active document.
        
        Returns:
            dict: Structured response containing status, message, and list of columns.
        """
        import traceback
        try:
            from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, BuiltInCategory, LocationPoint
            from collections import OrderedDict
            import math
            
            collector = FilteredElementCollector(self.doc).OfCategory(BuiltInCategory.OST_StructuralColumns).OfClass(FamilyInstance).WhereElementIsNotElementType().ToElements()
            columns_data = []
            
            for c in collector:
                loc = c.Location
                x = y = z = 0.0
                rotation = 0.0
                
                if isinstance(loc, LocationPoint):
                    pt = loc.Point
                    x, y, z = round(pt.X, 3), round(pt.Y, 3), round(pt.Z, 3)
                    rotation = round(math.degrees(loc.Rotation), 3)
                    
                base_param, top_param, base_offset_param, top_offset_param = self._get_column_level_parameters(c)
                
                base_level_id = None
                base_level_name = None
                if base_param and base_param.HasValue:
                    lvl = self.doc.GetElement(base_param.AsElementId())
                    if lvl:
                        base_level_id = lvl.UniqueId
                        base_level_name = lvl.Name
                        
                top_level_id = None
                top_level_name = None
                if top_param and top_param.HasValue:
                    lvl = self.doc.GetElement(top_param.AsElementId())
                    if lvl:
                        top_level_id = lvl.UniqueId
                        top_level_name = lvl.Name
                        
                base_offset = 0.0
                if base_offset_param and base_offset_param.HasValue:
                    base_offset = round(base_offset_param.AsDouble(), 3)
                    
                top_offset = 0.0
                if top_offset_param and top_offset_param.HasValue:
                    top_offset = round(top_offset_param.AsDouble(), 3)
                    
                col_dict = OrderedDict([
                    ("column_id", c.UniqueId),
                    ("column_type", self._get_symbol_name(c.Symbol)),
                    ("column_family", c.Symbol.FamilyName),
                    ("pinned", c.Pinned),
                    ("location", OrderedDict([("x", x), ("y", y), ("z", z)])),
                    ("rotation_degrees", rotation),
                    ("base_level_id", base_level_id),
                    ("base_level_name", base_level_name),
                    ("base_offset", base_offset),
                    ("top_level_id", top_level_id),
                    ("top_level_name", top_level_name),
                    ("top_offset", top_offset)
                ])
                columns_data.append(col_dict)
                
            return OrderedDict([
                ("status", "success"),
                ("message", "Successfully fetched all project structural columns."),
                ("data", OrderedDict([("columns", columns_data)]))
            ])
        except Exception as ex:
            return {
                "status": "error",
                "message": "fetch_all exception: " + str(ex) + "\n" + traceback.format_exc()
            }

    def fetch_types(self):
        """Queries and formats all loaded structural column family types.
        
        Returns:
            dict: Structured response containing status, message, and list of types.
        """
        import traceback
        try:
            from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol, BuiltInCategory
            from collections import OrderedDict
            
            collector = FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns)
            types_data = []
            
            for symbol in collector:
                types_data.append(OrderedDict([
                    ("column_type_id", symbol.UniqueId),
                    ("name", self._get_symbol_name(symbol)),
                    ("family_name", symbol.FamilyName)
                ]))
                
            return OrderedDict([
                ("status", "success"),
                ("message", "Successfully fetched structural column types."),
                ("data", OrderedDict([("column_types", types_data)]))
            ])
        except Exception as ex:
            return {
                "status": "error",
                "message": "fetch_types exception: " + str(ex) + "\n" + traceback.format_exc()
            }

    def create(self, x, y, base_level_id, top_level_id=None, base_offset=0.0, top_offset=0.0, rotation_degrees=0.0, column_type_id=None):
        """Places a new structural column family instance.
        
        Args:
            x (float): Placement X coordinate in feet.
            y (float): Placement Y coordinate in feet.
            base_level_id (str): UniqueId or Name of the base level.
            top_level_id (str, optional): UniqueId or Name of the top level.
            base_offset (float, optional): Base level height offset.
            top_offset (float, optional): Top level height offset.
            rotation_degrees (float, optional): Rotation angle in degrees around Z axis.
            column_type_id (str, optional): UniqueId of column type to place.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, XYZ, Line, ElementTransformUtils, FilteredElementCollector, FamilySymbol
        from Autodesk.Revit.DB.Structure import StructuralType
        from collections import OrderedDict
        import math
        
        base_level = self._get_level(base_level_id)
        if not base_level:
            return {"status": "error", "message": "Base level '{}' not found.".format(base_level_id)}
            
        symbol = None
        if column_type_id:
            symbol = self.doc.GetElement(column_type_id)
            if not symbol:
                for fs in FilteredElementCollector(self.doc).OfClass(FamilySymbol):
                    if self._get_symbol_name(fs).lower() == column_type_id.lower() or fs.UniqueId == column_type_id:
                        symbol = fs
                        break
            if not symbol:
                return {"status": "error", "message": "Structural column type '{}' not found.".format(column_type_id)}
                        
        if not symbol:
            symbol = self._get_default_column_symbol()
            
        if not symbol:
            return {"status": "error", "message": "No structural column family types loaded in the project."}
            
        z = base_level.Elevation
        location = XYZ(float(x), float(y), z)
        
        with Transaction(self.doc, "Agent - Create Structural Column") as trans:
            trans.Start()
            try:
                if not symbol.IsActive:
                    symbol.Activate()
                    self.doc.Regenerate()
                    
                new_col = self.doc.Create.NewFamilyInstance(location, symbol, base_level, StructuralType.Column)
                self.doc.Regenerate()
                
                base_param, top_param, base_offset_param, top_offset_param = self._get_column_level_parameters(new_col)
                
                if base_offset_param and not base_offset_param.IsReadOnly:
                    self._set_parameter_value(base_offset_param, base_offset)
                    
                if top_level_id:
                    top_lvl = self._get_level(top_level_id)
                    if top_lvl and top_param and not top_param.IsReadOnly:
                        top_param.Set(top_lvl.Id)
                        
                if top_offset_param and not top_offset_param.IsReadOnly:
                    self._set_parameter_value(top_offset_param, top_offset)
                    
                if rotation_degrees and float(rotation_degrees) != 0.0:
                    axis_pt1 = location
                    axis_pt2 = XYZ(location.X, location.Y, location.Z + 1.0)
                    axis_line = Line.CreateBound(axis_pt1, axis_pt2)
                    angle_rad = math.radians(float(rotation_degrees))
                    ElementTransformUtils.RotateElement(self.doc, new_col.Id, axis_line, angle_rad)
                    
                new_col.Pinned = True
                trans.Commit()
                
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column successfully created."),
                    ("data", OrderedDict([("element_id", new_col.UniqueId)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to create structural column: " + str(ex)}

    def modify(self, column_id, x=None, y=None, base_level_id=None, top_level_id=None, base_offset=None, top_offset=None, rotation_degrees=None, column_type_id=None):
        """Modifies attributes of an existing structural column instance.
        
        Args:
            column_id (str): UniqueId of the structural column to modify.
            x (float, optional): New X coordinate.
            y (float, optional): New Y coordinate.
            base_level_id (str, optional): UniqueId or name of new base level.
            top_level_id (str, optional): UniqueId or name of new top level.
            base_offset (float, optional): New base level offset height.
            top_offset (float, optional): New top level offset height.
            rotation_degrees (float, optional): New absolute rotation angle in degrees.
            column_type_id (str, optional): UniqueId or name of new column type symbol.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, XYZ, Line, ElementTransformUtils, LocationPoint, FilteredElementCollector, FamilySymbol, FamilyInstance, BuiltInCategory
        from collections import OrderedDict
        import math
        
        column = self.doc.GetElement(column_id)
        if not column or not isinstance(column, FamilyInstance) or column.Category.Id.IntegerValue != int(BuiltInCategory.OST_StructuralColumns):
            return {"status": "error", "message": "Structural column element not found."}
            
        with Transaction(self.doc, "Agent - Modify Structural Column") as trans:
            trans.Start()
            try:
                was_pinned = column.Pinned
                column.Pinned = False
                
                loc = column.Location
                if (x is not None or y is not None) and isinstance(loc, LocationPoint):
                    curr_pt = loc.Point
                    new_x = float(x) if x is not None else curr_pt.X
                    new_y = float(y) if y is not None else curr_pt.Y
                    new_z = curr_pt.Z
                    
                    if base_level_id:
                        lvl = self._get_level(base_level_id)
                        if lvl:
                            new_z = lvl.Elevation
                            
                    loc.Point = XYZ(new_x, new_y, new_z)
                    
                base_param, top_param, base_offset_param, top_offset_param = self._get_column_level_parameters(column)
                
                if base_level_id:
                    base_lvl = self._get_level(base_level_id)
                    if base_lvl and base_param and not base_param.IsReadOnly:
                        base_param.Set(base_lvl.Id)
                        
                if base_offset is not None:
                    self._set_parameter_value(base_offset_param, base_offset)
                        
                if top_level_id:
                    top_lvl = self._get_level(top_level_id)
                    if top_lvl and top_param and not top_param.IsReadOnly:
                        top_param.Set(top_lvl.Id)
                        
                if top_offset is not None:
                    self._set_parameter_value(top_offset_param, top_offset)
                        
                if rotation_degrees is not None and isinstance(loc, LocationPoint):
                    curr_rot_deg = math.degrees(loc.Rotation)
                    target_rot_deg = float(rotation_degrees)
                    delta_deg = target_rot_deg - curr_rot_deg
                    
                    if abs(delta_deg) > 1e-5:
                        center = loc.Point
                        axis_pt1 = center
                        axis_pt2 = XYZ(center.X, center.Y, center.Z + 1.0)
                        axis_line = Line.CreateBound(axis_pt1, axis_pt2)
                        angle_rad = math.radians(delta_deg)
                        ElementTransformUtils.RotateElement(self.doc, column.Id, axis_line, angle_rad)
                        
                if column_type_id:
                    symbol = self.doc.GetElement(column_type_id)
                    if not symbol:
                        for fs in FilteredElementCollector(self.doc).OfClass(FamilySymbol):
                            if self._get_symbol_name(fs).lower() == column_type_id.lower() or fs.UniqueId == column_type_id:
                                symbol = fs
                                break
                    if not symbol:
                        return {"status": "error", "message": "Structural column type '{}' not found.".format(column_type_id)}
                    if symbol:
                        if not symbol.IsActive:
                            symbol.Activate()
                            self.doc.Regenerate()
                        column.Symbol = symbol
                        
                column.Pinned = was_pinned
                trans.Commit()
                
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column successfully modified."),
                    ("data", OrderedDict([("element_id", column.UniqueId)]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to modify structural column: " + str(ex)}

    def delete(self, column_id):
        """Deletes an existing structural column instance.
        
        Args:
            column_id (str): UniqueId of the target structural column.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, FamilyInstance, BuiltInCategory
        from collections import OrderedDict
        
        column = self.doc.GetElement(column_id)
        if not column or not isinstance(column, FamilyInstance) or column.Category.Id.IntegerValue != int(BuiltInCategory.OST_StructuralColumns):
            return {"status": "error", "message": "Structural column element not found."}
            
        with Transaction(self.doc, "Agent - Delete Structural Column") as trans:
            trans.Start()
            try:
                column.Pinned = False
                self.doc.Delete(column.Id)
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column successfully deleted.")
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to delete structural column: " + str(ex)}

    def duplicate_type(self, column_type_id, new_type_name, dimensions=None):
        """Duplicates an existing structural column type and modifies its dimensions.
        
        Args:
            column_type_id (str): UniqueId or Name of the source type.
            new_type_name (str): Name for the newly created type.
            dimensions (dict, optional): Dict mapping parameter names to float values (feet).
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, FamilySymbol, FilteredElementCollector, BuiltInCategory
        from collections import OrderedDict
        
        # Verify type name uniqueness
        for fs in FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns):
            if self._get_symbol_name(fs).lower() == new_type_name.lower():
                return {"status": "error", "message": "Structural column type name '{}' already exists.".format(new_type_name)}
                
        symbol = self.doc.GetElement(column_type_id)
        if not symbol or not isinstance(symbol, FamilySymbol):
            # Try finding by name
            for fs in FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns):
                if self._get_symbol_name(fs).lower() == column_type_id.lower() or fs.UniqueId == column_type_id:
                    symbol = fs
                    break
                    
        if not symbol:
            return {"status": "error", "message": "Source structural column type not found."}
            
        with Transaction(self.doc, "Agent - Duplicate Structural Column Type") as trans:
            trans.Start()
            try:
                new_symbol = symbol.Duplicate(new_type_name)
                
                updated = []
                failed = []
                if dimensions:
                    for param_name, val in dimensions.items():
                        param = new_symbol.LookupParameter(param_name)
                        if param:
                            if self._set_parameter_value(param, val):
                                updated.append(param_name)
                            else:
                                failed.append("{} (failed to set)".format(param_name))
                        else:
                            failed.append("{} (not found)".format(param_name))
                            
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column type '{}' successfully created.".format(new_type_name)),
                    ("data", OrderedDict([
                        ("column_type_id", new_symbol.UniqueId),
                        ("updated_parameters", updated),
                        ("failed_parameters", failed)
                    ]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to duplicate type: " + str(ex)}

    def modify_type(self, column_type_id, dimensions):
        """Modifies parameters of an existing structural column type.
        
        Args:
            column_type_id (str): UniqueId or Name of the target type.
            dimensions (dict): Dict mapping parameter names to float values (feet).
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, FamilySymbol, FilteredElementCollector, BuiltInCategory
        from collections import OrderedDict
        
        symbol = self.doc.GetElement(column_type_id)
        if not symbol or not isinstance(symbol, FamilySymbol):
            # Try finding by name
            for fs in FilteredElementCollector(self.doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns):
                if self._get_symbol_name(fs).lower() == column_type_id.lower() or fs.UniqueId == column_type_id:
                    symbol = fs
                    break
                    
        if not symbol:
            return {"status": "error", "message": "Structural column type not found."}
            
        with Transaction(self.doc, "Agent - Modify Structural Column Type") as trans:
            trans.Start()
            try:
                updated = []
                failed = []
                for param_name, val in dimensions.items():
                    param = symbol.LookupParameter(param_name)
                    if param:
                        if self._set_parameter_value(param, val):
                            updated.append(param_name)
                        else:
                            failed.append("{} (failed to set)".format(param_name))
                    else:
                        failed.append("{} (not found)".format(param_name))
                        
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column type parameters successfully modified."),
                    ("data", OrderedDict([
                        ("column_type_id", symbol.UniqueId),
                        ("updated_parameters", updated),
                        ("failed_parameters", failed)
                    ]))
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to modify structural column type parameters: " + str(ex)}

    def delete_type(self, column_type_id):
        """Deletes a structural column type from the document.
        
        Args:
            column_type_id (str): UniqueId of the target structural column type.
            
        Returns:
            dict: Structured success/error response.
        """
        from Autodesk.Revit.DB import Transaction, FamilySymbol
        from collections import OrderedDict
        
        symbol = self.doc.GetElement(column_type_id)
        if not symbol or not isinstance(symbol, FamilySymbol):
            return {"status": "error", "message": "Structural column type not found."}
            
        with Transaction(self.doc, "Agent - Delete Structural Column Type") as trans:
            trans.Start()
            try:
                self.doc.Delete(symbol.Id)
                trans.Commit()
                return OrderedDict([
                    ("status", "success"),
                    ("message", "Structural column type successfully deleted.")
                ])
            except Exception as ex:
                trans.RollBack()
                return {"status": "error", "message": "Failed to delete structural column type: " + str(ex)}

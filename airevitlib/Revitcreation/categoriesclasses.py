# -*- coding: utf-8 -*-
import Autodesk.Revit.DB as DB

class CoordinateUtility(object):
    """Retrieves active Project Base Point offsets to align Level and Grid 
    origins cleanly in coordinates-offset models.
    """
    def __init__(self, doc):
        self.doc = doc
        self.translation = DB.XYZ.Zero
        
        # Query active Project Base Point
        base_point = DB.FilteredElementCollector(doc) \
            .OfCategory(DB.BuiltInCategory.OST_ProjectBasePoint) \
            .WhereElementIsNotElementType() \
            .FirstElement()
            
        if base_point:
            if hasattr(base_point, "Position"):
                self.translation = base_point.Position
            else:
                ew = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM).AsDouble()
                ns = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM).AsDouble()
                elev = base_point.get_Parameter(DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM).AsDouble()
                self.translation = DB.XYZ(ew, ns, elev)

    def transform_level(self, elevation_ft):
        """Translates level height by the Base Point's vertical offset."""
        return elevation_ft + self.translation.Z

    def transform_grid_point(self, x_ft, y_ft):
        """Translates grid coordinates horizontally relative to the Base Point."""
        return DB.XYZ(x_ft + self.translation.X, y_ft + self.translation.Y, self.translation.Z)


class LevelManager(object):
    """Manages creation, movement, copying, and deletion of Level elements."""
    SCALE = 3.280839895 # meters to decimal feet

    def __init__(self, doc, coord_utility):
        self.doc = doc
        self.coord = coord_utility

    def create(self, param_dict, geom_dict, rel_dict):
        elevation_ft = geom_dict.get("position_m", 0.0) * self.SCALE
        
        # Align level height relative to Project Base Point
        target_z = self.coord.transform_level(elevation_ft)
        level = DB.Level.Create(self.doc, target_z)
        
        default_name = "New Level " + str(level.Id.IntegerValue)
        level.Name = param_dict.get("name", default_name)
        return level

    def delete(self, element_id):
        elem = self.doc.GetElement(DB.ElementId(int(element_id)))
        if elem:
            if elem.Pinned:
                elem.Pinned = False
            self.doc.Delete(elem.Id)
        return True

    def move(self, element_id, geom_dict):
        level = self.doc.GetElement(DB.ElementId(int(element_id)))
        if level:
            new_elev_ft = geom_dict.get("position_m", 0.0) * self.SCALE
            target_z = self.coord.transform_level(new_elev_ft)
            level.Elevation = target_z
            return True
        return False

    def copy(self, element_id, translation_dict):
        source_lvl = self.doc.GetElement(DB.ElementId(int(element_id)))
        if source_lvl:
            offset_z_ft = translation_dict.get("z", 0.0) * self.SCALE
            new_elev_ft = source_lvl.Elevation + offset_z_ft
            new_level = DB.Level.Create(self.doc, new_elev_ft)
            new_level.Name = source_lvl.Name + " - Copy"
            return new_level
        return None


class GridManager(object):
    """Manages creation, movement, copying, and deletion of Grid elements."""
    SCALE = 3.280839895

    def __init__(self, doc, coord_utility):
        self.doc = doc
        self.coord = coord_utility

    def create(self, param_dict, geom_dict, rel_dict):
        pos_ft = geom_dict.get("position_m", 0.0) * self.SCALE
        axis = geom_dict.get("axis", "X").upper()
        
        start_ft = geom_dict.get("start_m", -30.0) * self.SCALE
        end_ft = geom_dict.get("end_m", 30.0) * self.SCALE

        # Align coordinate endpoints horizontally relative to Project Base Point
        if axis == "X":
            p1 = self.coord.transform_grid_point(pos_ft, start_ft)
            p2 = self.coord.transform_grid_point(pos_ft, end_ft)
        else:
            p1 = self.coord.transform_grid_point(start_ft, pos_ft)
            p2 = self.coord.transform_grid_point(end_ft, pos_ft)

        line = DB.Line.CreateBound(p1, p2)
        grid = DB.Grid.Create(self.doc, line)
        
        default_name = "New Grid " + str(grid.Id.IntegerValue)
        grid.Name = param_dict.get("name", default_name)
        return grid

    def delete(self, element_id):
        elem = self.doc.GetElement(DB.ElementId(int(element_id)))
        if elem:
            if elem.Pinned:
                elem.Pinned = False
            self.doc.Delete(elem.Id)
        return True

    def move(self, element_id, geom_dict):
        grid = self.doc.GetElement(DB.ElementId(int(element_id)))
        if grid:
            name = grid.Name
            self.doc.Delete(grid.Id)
            self.create({"name": name}, geom_dict, {})
            return True
        return False

    def copy(self, element_id, translation_dict):
        grid = self.doc.GetElement(DB.ElementId(int(element_id)))
        if grid:
            offset_x = translation_dict.get("x", 0.0) * self.SCALE
            offset_y = translation_dict.get("y", 0.0) * self.SCALE
            translation_vector = DB.XYZ(offset_x, offset_y, 0.0)
            new_ids = DB.ElementTransformUtils.CopyElement(self.doc, grid.Id, translation_vector)
            copied_grid = self.doc.GetElement(new_ids[0])
            copied_grid.Name = grid.Name + "_Copy"
            return copied_grid
        return None


class ColumnManager(object):
    """Manages placement and modification of structural column families."""
    SCALE = 3.280839895

    def __init__(self, doc, coord_utility):
        self.doc = doc
        self.coord = coord_utility

    def _find_symbol(self, family_name, type_name):
        collector = DB.FilteredElementCollector(self.doc).OfClass(DB.FamilySymbol)
        for sym in collector:
            if sym.Name == type_name or sym.Family.Name == family_name:
                return sym
        return None

    def create(self, param_dict, geom_dict, rel_dict):
        symbol = self._find_symbol(param_dict.get("family_name"), param_dict.get("type_name"))
        if not symbol:
            symbol = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsElementType().FirstElement()
            
        if symbol and not symbol.IsActive:
            symbol.Activate()

        point_m = geom_dict.get("points", [{"x": 0.0, "y": 0.0}])[0]
        
        # Align column horizontal placement relative to Project Base Point
        xyz = self.coord.transform_grid_point(point_m.get("x", 0.0) * self.SCALE, point_m.get("y", 0.0) * self.SCALE)
        
        structural_type = DB.Structure.StructuralType.Column
        col_inst = self.doc.Create.NewFamilyInstance(xyz, symbol, structural_type)
        
        base_lvl_id = rel_dict.get("base_constraint_id")
        if base_lvl_id:
            # We do not need to offset base constraint id as it is resolved directly by Level Element
            base_p = col_inst.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
            if base_p:
                base_p.Set(DB.ElementId(int(base_lvl_id)))
        return col_inst

    def delete(self, element_id):
        elem = self.doc.GetElement(DB.ElementId(int(element_id)))
        if elem:
            if elem.Pinned:
                elem.Pinned = False
            self.doc.Delete(elem.Id)
        return True

    def move(self, element_id, geom_dict):
        col = self.doc.GetElement(DB.ElementId(int(element_id)))
        if col:
            point_m = geom_dict.get("points", [{"x": 0.0, "y": 0.0}])[0]
            new_xyz = self.coord.transform_grid_point(point_m.get("x", 0.0) * self.SCALE, point_m.get("y", 0.0) * self.SCALE)
            loc = col.Location
            if isinstance(loc, DB.LocationPoint):
                offset_vector = new_xyz - loc.Point
                DB.ElementTransformUtils.MoveElement(self.doc, col.Id, offset_vector)
                return True
        return False

    def copy(self, element_id, translation_dict):
        col = self.doc.GetElement(DB.ElementId(int(element_id)))
        if col:
            offset_x = translation_dict.get("x", 0.0) * self.SCALE
            offset_y = translation_dict.get("y", 0.0) * self.SCALE
            translation_vector = DB.XYZ(offset_x, offset_y, 0.0)
            new_ids = DB.ElementTransformUtils.CopyElement(self.doc, col.Id, translation_vector)
            return self.doc.GetElement(new_ids[0])
        return None


class FoundationManager(object):
    """Manages placement of structural isolated foundation family components."""
    SCALE = 3.280839895

    def __init__(self, doc, coord_utility):
        self.doc = doc
        self.coord = coord_utility

    def _find_symbol(self):
        return DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_StructuralFoundation).WhereElementIsElementType().FirstElement()

    def create(self, param_dict, geom_dict, rel_dict):
        symbol = self._find_symbol()
        if symbol and not symbol.IsActive:
            symbol.Activate()
            
        point_m = geom_dict.get("points", [{"x": 0.0, "y": 0.0}])[0]
        
        # Align foundation horizontal placement relative to Project Base Point
        xyz = self.coord.transform_grid_point(point_m.get("x", 0.0) * self.SCALE, point_m.get("y", 0.0) * self.SCALE)
        
        structural_type = DB.Structure.StructuralType.Footing
        found_inst = self.doc.Create.NewFamilyInstance(xyz, symbol, structural_type)
        return found_inst

    def delete(self, element_id):
        elem = self.doc.GetElement(DB.ElementId(int(element_id)))
        if elem:
            if elem.Pinned:
                elem.Pinned = False
            self.doc.Delete(elem.Id)
        return True

    def move(self, element_id, geom_dict):
        found = self.doc.GetElement(DB.ElementId(int(element_id)))
        if found:
            point_m = geom_dict.get("points", [{"x": 0.0, "y": 0.0}])[0]
            new_xyz = self.coord.transform_grid_point(point_m.get("x", 0.0) * self.SCALE, point_m.get("y", 0.0) * self.SCALE)
            loc = found.Location
            if isinstance(loc, DB.LocationPoint):
                offset_vector = new_xyz - loc.Point
                DB.ElementTransformUtils.MoveElement(self.doc, found.Id, offset_vector)
                return True
        return False

    def copy(self, element_id, translation_dict):
        found = self.doc.GetElement(DB.ElementId(int(element_id)))
        if found:
            offset_x = translation_dict.get("x", 0.0) * self.SCALE
            offset_y = translation_dict.get("y", 0.0) * self.SCALE
            translation_vector = DB.XYZ(offset_x, offset_y, 0.0)
            new_ids = DB.ElementTransformUtils.CopyElement(self.doc, found.Id, translation_vector)
            return self.doc.GetElement(new_ids[0])
        return None


class BIMExecutionEngine:
    """The central state controller and sequence manager."""
    SCALE = 3.280839895

    def __init__(self, doc):
        self.doc = doc
        
        # 1. Initialize coordinate offset tracker
        self.coord = CoordinateUtility(doc)
        
        # 2. Inject coordinate utility into managers to enable offset alignment
        self.managers = {
            "level": LevelManager(doc, self.coord),
            "grid": GridManager(doc, self.coord),
            "column": ColumnManager(doc, self.coord),
            "foundation": FoundationManager(doc, self.coord)
        }

    def load_current_state(self):
        """Scrapes the live active Revit document elements, calculates project 
        extents and bounding boxes, and formats them into our unified dictionary schema.
        """
        state = {
            "levels": [],
            "grids": [],
            "columns": [],
            "foundations": []
        }

        # 1. Scan Levels
        levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).WhereElementIsNotElementType().ToElements()
        for lvl in levels:
            # Report elevation relative to the Project Base Point so AI tracks it natively
            rel_elevation_ft = lvl.Elevation - self.coord.translation.Z
            state["levels"].append({
                "id": str(lvl.Id.IntegerValue),
                "name": lvl.Name,
                "elevation_m": round(rel_elevation_ft / self.SCALE, 3)
            })

        # 2. Scan Grids
        grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).WhereElementIsNotElementType().ToElements()
        for grd in grids:
            curve = grd.Curve
            axis = "X"
            pos_m = 0.0
            if curve and isinstance(curve, DB.Line):
                start = curve.GetEndPoint(0)
                end = curve.GetEndPoint(1)
                
                # Report horizontal coordinates relative to the Project Base Point offset
                rel_start_x = start.X - self.coord.translation.X
                rel_start_y = start.Y - self.coord.translation.Y
                direction = end - start
                
                if abs(direction.X) < 0.001:
                    axis = "X"
                    pos_m = round(rel_start_x / self.SCALE, 3)
                else:
                    axis = "Y"
                    pos_m = round(rel_start_y / self.SCALE, 3)

            state["grids"].append({
                "id": str(grd.Id.IntegerValue),
                "name": grd.Name,
                "axis": axis,
                "position_m": pos_m
            })

        # 3. Scan Columns
        columns = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements()
        for col in columns:
            loc = col.Location
            pos = {"x": 0.0, "y": 0.0, "z": 0.0}
            if isinstance(loc, DB.LocationPoint):
                pos = {
                    "x": round((loc.Point.X - self.coord.translation.X) / self.SCALE, 3),
                    "y": round((loc.Point.Y - self.coord.translation.Y) / self.SCALE, 3),
                    "z": round((loc.Point.Z - self.coord.translation.Z) / self.SCALE, 3)
                }
            state["columns"].append({
                "id": str(col.Id.IntegerValue),
                "type": col.Name,
                "position_m": pos
            })

        # 4. Scan Foundations
        foundations = DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_StructuralFoundation).WhereElementIsNotElementType().ToElements()
        for fnd in foundations:
            loc = fnd.Location
            pos = {"x": 0.0, "y": 0.0, "z": 0.0}
            if isinstance(loc, DB.LocationPoint):
                pos = {
                    "x": round((loc.Point.X - self.coord.translation.X) / self.SCALE, 3),
                    "y": round((loc.Point.Y - self.coord.translation.Y) / self.SCALE, 3),
                    "z": round((loc.Point.Z - self.coord.translation.Z) / self.SCALE, 3)
                }
            state["foundations"].append({
                "id": str(fnd.Id.IntegerValue),
                "type": fnd.Name,
                "position_m": pos
            })

        # --- CALCULATE PHYSICAL MODEL EXTENTS & SPATIAL BOUNDS ---
        x_coords = []
        y_coords = []
        for g in state["grids"]:
            pos = g["position_m"]
            if g["axis"] == "X":
                x_coords.append(pos)
            else:
                y_coords.append(pos)

        x_min, x_max = (min(x_coords), max(x_coords)) if x_coords else (0.0, 0.0)
        y_min, y_max = (min(y_coords), max(y_coords)) if y_coords else (0.0, 0.0)
        
        x_span = round(x_max - x_min, 2)
        y_span = round(y_max - y_min, 2)
        
        z_coords = [lvl["elevation_m"] for lvl in state["levels"]]
        z_min, z_max = (min(z_coords), max(z_coords)) if z_coords else (0.0, 0.0)
        height_span = round(z_max - z_min, 2)
        
        project_title = "Untitled Revit Project"
        try:
            if self.doc.ProjectInformation:
                project_title = self.doc.ProjectInformation.Name or self.doc.Title
        except:
            pass

        state["project_metadata"] = {
            "project_title": project_title,
            "building_height_m": height_span,
            "existing_grid_x_span_m": x_span if x_span > 0.0 else 30.0,
            "existing_grid_y_span_m": y_span if y_span > 0.0 else 30.0,
            "bounding_box_min_m": {"x": round(x_min, 2), "y": round(y_min, 2), "z": round(z_min, 2)},
            "bounding_box_max_m": {"x": round(x_max, 2), "y": round(y_max, 2), "z": round(z_max, 2)}
        }

        return state

    def execute_transaction(self, instructions_list):
        """Applies sequential instructions within a transaction context. 
        Returns True/False based on execution outcome.
        """
        t = DB.Transaction(self.doc, "AI BIM Agent - Execute Action Series")
        t.Start()
        
        try:
            for instr in instructions_list:
                action = instr["action"]
                category = instr["category"]
                manager = self.managers.get(category)
                
                if not manager:
                    continue

                if action == "create":
                    manager.create(
                        instr.get("parameters", {}),
                        instr.get("geometry", {}),
                        instr.get("relationships", {})
                    )
                elif action == "delete":
                    manager.delete(instr["element_id"])
                elif action == "move" or action == "update":
                    manager.move(instr["element_id"], instr.get("geometry", {}))
                elif action == "copy":
                    manager.copy(instr["element_id"], instr.get("parameters", {}).get("translation", {}))

            t.Commit()
            
            # visual extents transaction
            t_extents = DB.Transaction(self.doc, "AI BIM Agent - Optimize Visual Extents")
            t_extents.Start()
            self.doc.Regenerate()
            
            all_levels = DB.FilteredElementCollector(self.doc).OfClass(DB.Level).WhereElementIsNotElementType()
            for lvl in all_levels:
                try:
                    lvl.Maximize3DExtents()
                except:
                    pass
            
            all_grids = DB.FilteredElementCollector(self.doc).OfClass(DB.Grid).WhereElementIsNotElementType()
            for grd in all_grids:
                try:
                    grd.Maximize3DExtents()
                except:
                    pass
                    
            t_extents.Commit()
            return True
        except Exception as err:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            print("Database transaction aborted: {}".format(err))
            return False
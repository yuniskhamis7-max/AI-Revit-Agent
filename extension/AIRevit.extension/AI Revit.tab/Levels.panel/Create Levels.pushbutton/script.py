#! python3
import os
import sys

BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI") # <--- ADDED REQUIRED REFERENCE FOR UI
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI # <--- ADDED NATIVE REVIT UI

# Safely reload the module only if it has already been loaded into memory
import importlib
if 'lib.Levels' in sys.modules:
    importlib.reload(sys.modules['lib.Levels'])

from lib.Levels import Level, SimpleTransaction

# Get Document safely
doc = __revit__.ActiveUIDocument.Document

# ==========================================
# 1. OPTIONAL: GET A LINKED MODEL
# ==========================================
link_instances = DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements()
arch_link = link_instances[0] if link_instances else None

# ==========================================
# 2. INITIALIZE LEVEL OBJECTS
# ==========================================
lvl_basement = Level(doc, name="B01 - Basement")
lvl_ground   = Level(doc, name="L00 - Ground Floor")
lvl_first    = Level(doc, name="L01 - First Floor")

new_levels = [lvl_basement, lvl_ground, lvl_first]
keep_level_names = [lvl.name for lvl in new_levels]

# ==========================================
# 3. DRAFT THE LEVELS
# ==========================================
lvl_basement.create_at_elevation(elevation=-3000, unit="mm", measure_from="PBP")

if arch_link:
    lvl_ground.create_from_link(link_instance=arch_link, source_level_name="Ground")
else:
    lvl_ground.create_at_elevation(elevation=0, unit="mm", measure_from="PBP")

lvl_first.create_by_offset(ref_level=lvl_ground, z_offset=4500, unit="mm")

# Finalize the new levels (Generate Views and Pin them!)
for lvl in new_levels:
    if lvl.exists:
        lvl.create_floor_plan()
        lvl.pin()

# ==========================================
# 4. CLEANUP: PROMPT AND DELETE OLD LEVELS
# ==========================================
all_existing_levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()

old_levels = [lvl for lvl in all_existing_levels if lvl.Name not in keep_level_names]

if old_levels:
    # 4a. REPLACED PYREVIT FORMS WITH NATIVE REVIT TASK DIALOG
    msg = "There are {} old levels in this project. Do you want to delete them? (This will bypass pins).".format(len(old_levels))
    
    dialog = UI.TaskDialog("Cleanup Old Levels?")
    dialog.MainInstruction = "Cleanup Old Levels?"
    dialog.MainContent = msg
    dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
    dialog.DefaultButton = UI.TaskDialogResult.No
    
    # Show dialog to user
    result = dialog.Show()
    user_wants_to_delete = (result == UI.TaskDialogResult.Yes)

    # 4b. DELETE IF USER AGREED
    if user_wants_to_delete:
        with SimpleTransaction(doc, "Delete Old Levels"):
            for old_lvl in old_levels:
                try:
                    if old_lvl.Pinned:
                        old_lvl.Pinned = False
                    
                    deleted_name = old_lvl.Name
                    
                    doc.Delete(old_lvl.Id)
                    
                    print("Deleted old level: {}".format(deleted_name))
                except Exception as e:
                    print("Could not delete level ID {}. Error: {}".format(old_lvl.Id, e))
    else:
        print("Skipped deleting old levels.")

print("== Level System Updated Successfully! ==")
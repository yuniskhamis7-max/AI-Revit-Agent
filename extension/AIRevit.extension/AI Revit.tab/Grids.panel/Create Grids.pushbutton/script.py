#! python3
"""pyRevit entrypoint for manual grid creation experiments.

This button currently runs several demonstration scenarios against the active
model. Treat it as a development command until it is replaced by payload-driven
execution.
"""

import os
import sys

BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB

import importlib
if 'lib.Grids' in sys.modules:
    importlib.reload(sys.modules['lib.Grids'])

from lib.Grids import Grid 

doc = __revit__.ActiveUIDocument.Document
links = DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements()

# ==============================================================================
# Development scenarios
#
# The loop intentionally exercises every scenario for quick manual testing. For
# a production button, replace this with explicit user selection or payload
# validation before writing to the Revit document.
# ==============================================================================

for ACTIVE_SCENARIO in range(1, 6):

    print("Running Scenario {}...".format(ACTIVE_SCENARIO))

    if ACTIVE_SCENARIO == 1:
        # ----------------------------------------------------------------------
        # SCENARIO 1: NO LINK
        # We know the dimensions (e.g., 30,000mm length, 20,000mm width).
        # ----------------------------------------------------------------------
        grid_1 = Grid(doc, "1")
        grid_A = Grid(doc, "A")

        # X-Axis grid (Horizontal). Span manually set from 0 to 30,000.
        grid_1.create_anchor(direction="X", placement_coord=0, span_reference=(0, 30000))
        
        # Y-Axis grid (Vertical). Span manually set from 0 to 20,000.
        grid_A.create_anchor(direction="Y", placement_coord=0, span_reference=(0, 20000))

        # Draft the rest based on offsets
        grid_2 = Grid(doc, "2")
        grid_B = Grid(doc, "B")
        grid_2.create_by_offset(grid_1, vector=(0, 5000, 0))
        grid_B.create_by_offset(grid_A, vector=(6000, 0, 0))


    elif ACTIVE_SCENARIO == 2:
        # ----------------------------------------------------------------------
        # SCENARIO 2: WE HAVE A LINK, AND WE WANT TO COPY GRIDS FROM IT
        # We DO NOT know the names of the grids. The class handles it.
        # ----------------------------------------------------------------------
        if not links:
            print("Error: No links found for Scenario 2.")
        else:
            main_link = links[0]
            
            # Read all eligible grid names from the link and duplicate them.
            copied_grids = Grid.copy_all_from_link(doc, main_link)
            
            for cg in copied_grids:
                cg.pin() # Automatically pin all monitored grids
                print("Copied Grid: {}".format(cg.name))


    elif ACTIVE_SCENARIO == 3:
        # ----------------------------------------------------------------------
        # SCENARIO 3: WE HAVE A LINK, BUT WE WANT TO DRAFT FROM SCRATCH
        # We want our grids to automatically stretch to the boundaries of the link.
        # ----------------------------------------------------------------------
        if not links:
            print("Error: No links found for Scenario 3.")
        else:
            main_link = links[0]
            
            grid_1 = Grid(doc, "1")
            grid_A = Grid(doc, "A")

            # Passing the link as the span_reference. It reads the Link's BoundingBox!
            grid_1.create_anchor("X", placement_coord=0, span_reference=main_link, padding=2000)
            grid_A.create_anchor("Y", placement_coord=0, span_reference=main_link, padding=2000)
            
            # Draft the rest based on offsets
            grid_2 = Grid(doc, "2")
            grid_2.create_by_offset(grid_1, vector=(0, 4500, 0))


    elif ACTIVE_SCENARIO == 4:
        # ----------------------------------------------------------------------
        # SCENARIO 4: WE HAVE MANY LINKS, BUT DRAFT FROM SCRATCH
        # We want grids to stretch to cover ALL links in the model combined.
        # ----------------------------------------------------------------------
        grid_1 = Grid(doc, "1")
        grid_A = Grid(doc, "A")

        # "Auto" automatically merges the bounding boxes of ALL links in the model.
        grid_1.create_anchor("X", placement_coord=0, span_reference="Auto", padding=3000)
        grid_A.create_anchor("Y", placement_coord=0, span_reference="Auto", padding=3000)


    elif ACTIVE_SCENARIO == 5:
        # ----------------------------------------------------------------------
        # SCENARIO 5: WE HAVE MANY LINKS, COPY FROM ONE SPECIFIC LINK
        # e.g., We have a Structural link and Arch link, we only want Arch grids.
        # ----------------------------------------------------------------------
        if len(links) < 2:
            print("Warning: You need at least 2 links to test this properly.")
            
        if links:
            # Let's say we identify the link by its name containing "Arch"
            target_link = next((lnk for lnk in links if "Arch" in lnk.Name), links[0])
            
            print("Targeting link: {}".format(target_link.Name))
            copied_grids = Grid.copy_all_from_link(doc, target_link)
            
            for cg in copied_grids:
                cg.pin()
                print("Copied: {}".format(cg.name))


print("== Script Execution Complete ==")

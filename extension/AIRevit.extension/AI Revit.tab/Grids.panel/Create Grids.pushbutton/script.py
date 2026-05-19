#! python3

import os
import sys

BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lib.Grids import Grid 

doc = __revit__.ActiveUIDocument.Document

# ==========================================
# 1. HORIZONTAL GRIDS (1, 2, 3, 4)
# ==========================================
# Let's say our bay spacings are: 3000mm, 4500mm, 3000mm

grid_1 = Grid(doc, name="1")
grid_2 = Grid(doc, name="2")
grid_3 = Grid(doc, name="3")
grid_4 = Grid(doc, name="4")

# Place the anchor grid. (X-direction, 20 meters long)
grid_1.create_by_length(start_pt=(0, 0, 0), direction="X", length=20000)

# Now, just offset the remaining grids in the Y-direction!
grid_2.create_by_offset(ref_grid=grid_1, vector=(0, 3000, 0)) # 3000mm from Grid 1
grid_3.create_by_offset(ref_grid=grid_2, vector=(0, 4500, 0)) # 4500mm from Grid 2
grid_4.create_by_offset(ref_grid=grid_3, vector=(0, 3000, 0)) # 3000mm from Grid 3


# ==========================================
# 2. VERTICAL GRIDS (A, B, C)
# ==========================================
# Let's say our bay spacings are: 5000mm, 6000mm

grid_A = Grid(doc, name="A")
grid_B = Grid(doc, name="B")
grid_C = Grid(doc, name="C")

# Place the anchor grid slightly below the first grid so they intersect nicely
# (Y-direction, 15 meters long)
grid_A.create_by_length(start_pt=(-2000, -2000, 0), direction="Y", length=15000)

# Offset the remaining grids in the X-direction!
grid_B.create_by_offset(ref_grid=grid_A, vector=(5000, 0, 0)) # 5000mm from Grid A
grid_C.create_by_offset(ref_grid=grid_B, vector=(6000, 0, 0)) # 6000mm from Grid B


print("== Grid System created using drafting offsets! ==")

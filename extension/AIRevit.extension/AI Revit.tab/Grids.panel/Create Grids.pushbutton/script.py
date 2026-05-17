"""pyRevit entrypoint for grid payload execution."""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pyrevit import revit
from lib.Grids import Grid # Importing from your lib folder

doc = revit.doc

# Initialize a grid object
grid_1 = Grid(doc, name="1")

# Because we set the default to "PBP", this will automatically 
# measure 5000mm starting from the Project Base Point!
grid_1.create_straight(
    start_pt=(0, 0, 2000), 
    end_pt=(0, 5000, 2000), 
    unit="mm"
)

print("Grid created relative to Project Base Point!")

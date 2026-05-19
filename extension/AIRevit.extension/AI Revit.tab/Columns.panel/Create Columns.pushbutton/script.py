"""pyRevit entrypoint for future column payload execution.

This placeholder only prepares imports from the repository root. The intended
next step is to load validated column entries from ``payload.json`` and place
matching Revit family instances between existing levels.
"""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)



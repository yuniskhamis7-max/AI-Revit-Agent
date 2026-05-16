"""pyRevit entrypoint for AI payload generation."""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from revit.ui import show_execution_result
from run import generate_payload


show_execution_result(generate_payload())

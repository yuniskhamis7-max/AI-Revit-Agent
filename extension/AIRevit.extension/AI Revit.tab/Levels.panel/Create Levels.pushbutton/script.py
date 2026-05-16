"""pyRevit entrypoint for level payload execution."""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from revit.ui import get_active_document, show_execution_result, show_validation_errors
from run import run_category


result = run_category(get_active_document(), "levels")
if result["success"]:
    show_execution_result(result)
elif not result.get("results"):
    show_execution_result(result)
else:
    show_validation_errors(result.get("results", []))

"""pyRevit button entrypoint for the AI Revit Agent.

This file is intentionally tiny. It only makes the project root importable,
then hands control to the runtime executor.
"""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from runtime.executor import run


run()

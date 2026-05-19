"""pyRevit entrypoint for future AI payload generation.

This placeholder only prepares imports from the repository root. The intended
next step is to turn a user instruction into the schema documented in
``docs/PAYLOAD_SCHEMA.md`` and save it as ``payload.json`` for review.
"""

import os
import sys


BUTTON_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BUTTON_DIR, "..", "..", "..", "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


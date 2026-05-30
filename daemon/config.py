# -*- coding: utf-8 -*-
import os
import sys

# Retrieve the key from the persistent Windows environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: The GEMINI_API_KEY environment variable is not configured.")
    print("Please set it permanently using: setx GEMINI_API_KEY \"your_key\"")
    sys.exit(1)

REVIT_BRIDGE_URL = "http://127.0.0.1:8080/execute/"

# Define your preferred active model here:
# - "gemini-2.5-flash" (Optimized for speed, low latency tool calling)
# - "gemini-2.5-pro"   (Optimized for complex, multi-step geometric reasoning)
ACTIVE_MODEL = "gemini-2.5-flash"
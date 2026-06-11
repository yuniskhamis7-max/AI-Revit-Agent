# -*- coding: utf-8 -*-
"""State-persistent routing engine and core datum tools for Revit Agent Bridge."""

import clr
import os
import sys
from collections import OrderedDict

# Setup Port Configuration
PORT = 8080

# Load the C# Assembly
current_dir = os.path.dirname(__file__)
dll_path = os.path.join(current_dir, "RevitAgentBridge.dll")

if not os.path.exists(dll_path):
    print(">>> ERROR: RevitAgentBridge.dll not found in: {}".format(current_dir))
    sys.exit()

try:
    clr.AddReferenceToFileAndPath(dll_path)
except Exception as e:
    print(">>> ERROR: Failed to load RevitAgentBridge.dll: {}".format(str(e)))
    sys.exit()

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import ExternalEvent
from RevitAgentBridge import AgentExternalEventHandler, BridgeServer, BridgeRegistry

# =====================================================================
# IMPORT DECOUPLED TOOL REGISTRY & ROUTING ENGINE
# =====================================================================

# Ensure local directory is in path for imports
if current_dir not in sys.path:
    sys.path.append(current_dir)

import tools
registry = tools.registry

router_executor = registry.execute

if BridgeRegistry.ActiveServer is not None:
    try:
        BridgeRegistry.ActiveServer.Stop()
        BridgeRegistry.ActiveServer = None
        BridgeRegistry.ActiveEvent = None
        print(">>> [STOPPED] AI-Revit Agent Bridge.")
    except Exception as ex:
        print(">>> ERROR: Failed to cleanly stop server: " + str(ex))
else:
    try:
        handler = AgentExternalEventHandler()
        handler.PythonExecutor = router_executor

        external_event = ExternalEvent.Create(handler)

        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(PORT)

        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent = external_event

        print(">>> [STARTED] AI-Revit Agent Bridge running on Port {}.".format(PORT))
        print(">>> Agnostic backend interface ready.")
    except Exception as ex:
        print(">>> ERROR: Failed to start the Bridge Server: " + str(ex))
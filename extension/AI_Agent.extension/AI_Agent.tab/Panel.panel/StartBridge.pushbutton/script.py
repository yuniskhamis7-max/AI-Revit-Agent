# -*- coding: utf-8 -*-
import clr
import os
import sys
from pyrevit import script

current_dir = os.path.dirname(__file__)
dll_name = "RevitAgentBridge.dll"
dll_full_path = os.path.join(current_dir, dll_name)

output = script.get_output()

# Safely resolve the binary dependencies
if os.path.exists(dll_full_path):
    try:
        clr.AddReferenceToFileAndPath(dll_full_path)
    except Exception as ex:
        output.print_html("<p style='color:red;'><b>Assembly Loading Failure:</b> {}</p>".format(str(ex)))
        sys.exit()
else:
    output.print_html("<p style='color:red;'><b>Missing Component:</b> RevitAgentBridge.dll not found in pushbutton folder.</p>")
    sys.exit()

# Import the bridge components from our namespace
from RevitAgentBridge import AgentExternalEventHandler, BridgeServer, BridgeRegistry
from Autodesk.Revit.UI import ExternalEvent

def stop_active_bridge():
    """Tears down the active server registry reference."""
    try:
        active_server = BridgeRegistry.ActiveServer
        if active_server is not None:
            active_server.Stop()
            BridgeRegistry.ActiveServer = None
            output.print_html("<p style='color:orange;'><b>Bridge Stopped:</b> Port 8080 has been released.</p>")
    except Exception as ex:
         output.print_html("<p style='color:red;'><b>Error stopping active bridge:</b> {}</p>".format(str(ex)))

# Toggle server execution using the static registry
if BridgeRegistry.ActiveServer is not None:
    stop_active_bridge()
else:
    try:
        # Instantiate events
        handler = AgentExternalEventHandler()
        external_event = ExternalEvent.Create(handler)

        # Start the background HTTP loop
        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(8080)

        # Save to our static C# class to prevent garbage collection
        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent = external_event
        output.print_html("<p style='color:green;'><b>Bridge Active:</b> Listener running on http://127.0.0.1:8080/execute/</p>")
    except Exception as ex:
        output.print_html("<p style='color:red;'><b>Bridge Initialization Error:</b> {}</p>".format(str(ex)))
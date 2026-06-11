# -*- coding: utf-8 -*-
import urllib.request
import json
import time

def send_payload(request_json):
    """Sends a raw JSON string to Revit, pretty-prints the request and response, and returns the response."""
    url = "http://127.0.0.1:8080/execute"
    
    # 1. Parse and format the Request JSON for clean printing
    try:
        req_data = json.loads(request_json)
        tool_name = req_data.get("tool", "unknown")
        formatted_req = json.dumps(req_data, indent=2)
    except Exception:
        tool_name = "unknown"
        formatted_req = request_json

    # Print Request Box
    print("\n" + "=" * 60)
    print(">>> REQUEST: {}".format(tool_name))
    print("-" * 60)
    print(formatted_req)
    print("-" * 60)
    
    req = urllib.request.Request(
        url,
        data=request_json.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            response_json = response.read().decode("utf-8")
            
            # 2. Parse and format the Response JSON for clean printing
            try:
                res_data = json.loads(response_json)
                status = res_data.get("status", "unknown").upper()
                formatted_res = json.dumps(res_data, indent=2)
            except Exception:
                status = "UNKNOWN"
                formatted_res = response_json
            
            print("<<< RESPONSE (Status: {})".format(status))
            print("-" * 60)
            print(formatted_res)
            print("=" * 60)
            return response_json
            
    except Exception as e:
        err_data = {"status": "error", "message": str(e)}
        err_json = json.dumps(err_data, indent=2)
        print("<<< RESPONSE (CONNECTION ERROR)")
        print("-" * 60)
        print(err_json)
        print("=" * 60)
        return json.dumps(err_data)


# =====================================================================
# GRID & LEVEL ALIGNMENT TEST SEQUENCE
# =====================================================================
if __name__ == "__main__":
    print("[*] Starting sequential alignment tests...")

    # Step 1: Query Level Extents to extract coordinates
    levels_res_text = send_payload('{"tool": "fetch_levels", "input": {}}')
    time.sleep(3)

    try:
        levels_data = json.loads(levels_res_text)
        levels_list = levels_data.get("data", {}).get("levels", [])
        if levels_list:
            # Extract boundaries from the first level's 3D model extents
            first_level = levels_list[0]
            min_x = float(first_level["model_extent_start"]["x"])
            min_y = float(first_level["model_extent_start"]["y"])
            max_x = float(first_level["model_extent_end"]["x"])
            max_y = float(first_level["model_extent_end"]["y"])
        else:
            # Default fallbacks if no level geometry exists
            min_x, min_y, max_x, max_y = 0.0, 0.0, 100.0, 100.0
    except Exception as e:
        print("[!] Failed to parse levels. Using fallbacks. Error: " + str(e))
        min_x, min_y, max_x, max_y = 0.0, 0.0, 100.0, 100.0

    print("[*] Extents resolved: X_range({} to {}), Y_range({} to {})".format(min_x, max_x, min_y, max_y))

    # Step 2: Create "Old Grid" (offset from the true level boundary)
    old_grid_payload = json.dumps({
        "tool": "create_grid",
        "input": {
            "name": "Old-Grid-A",
            "start_x": min_x - 20.0,  # Offset to the left
            "start_y": min_y - 10.0,  # Offset down
            "end_x": min_x - 20.0,
            "end_y": max_y + 10.0
        }
    })
    old_grid_res = send_payload(old_grid_payload)
    
    try:
        old_grid_data = json.loads(old_grid_res)
        old_grid_id = old_grid_data.get("data", {}).get("element_id")
    except Exception:
        old_grid_id = None
    time.sleep(3)

    # Step 3: Create a "New Grid" defined directly by the level's X extents
    new_grid_payload = json.dumps({
        "tool": "create_grid",
        "input": {
            "name": "New-Grid-B",
            "start_x": min_x,
            "start_y": min_y,
            "end_x": max_x,
            "end_y": min_y
        }
    })
    send_payload(new_grid_payload)
    time.sleep(3)

    # Step 4: Modify the "Old Grid" to align with the starting point and span of the "New Grid"
    if old_grid_id:
        modify_old_grid_payload = json.dumps({
            "tool": "modify_grid",
            "input": {
                "grid_id": old_grid_id,
                "name": "Old-Grid-A-ALIGNED",
                "start_x": min_x,
                "start_y": min_y,
                "end_x": max_x,
                "end_y": min_y
            }
        })
        send_payload(modify_old_grid_payload)
        time.sleep(3)
    else:
        print("[!] Old Grid ID was not successfully captured. Skipping alignment modification step.")

    # Step 5: Fetch grids to verify coordinates and alignment results
    send_payload('{"tool": "fetch_grids", "input": {}}')
    
    print("\n[*] Alignment tests completed.")
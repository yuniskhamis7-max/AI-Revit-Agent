#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Revit AI Agent — Tool Runner Utility (run_tool.py)

A developer-friendly CLI for executing and testing Revit bridge tools directly.
Supports listing tools, inspecting schemas, single executions, command chaining (--then),
and batch processing (.txt or .json files).

Usage:
  python run_tool.py list
  python run_tool.py show <tool_name>
  python run_tool.py run <tool_name> [key=value ...] [--then <tool_name2> [key=value ...] ...]
  python run_tool.py batch <file_path>
"""
import sys
import json
import urllib.request
import urllib.error
import shlex
import os

BRIDGE_URL = "http://127.0.0.1:8080"

def print_separator(char="=", length=60):
    print(char * length)

def query_bridge(endpoint, method="GET", payload=None):
    """Sends a request to the Revit bridge server and returns response dict."""
    url = "{}{}".format(BRIDGE_URL, endpoint)
    headers = {"Content-Type": "application/json"}
    
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            res_body = res.read().decode("utf-8")
            return json.loads(res_body)
    except urllib.error.URLError as e:
        return {
            "status": "error",
            "message": "Cannot reach Revit Bridge at {}. Make sure Revit is running, the model is open, and the bridge is active. Error: {}".format(BRIDGE_URL, e)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "Unexpected error communication with bridge: {}".format(e)
        }

def parse_val(val_str):
    """Autodetects and casts string inputs to python types (int, float, bool, json)."""
    # Boolean check
    if val_str.lower() == "true":
        return True
    if val_str.lower() == "false":
        return False
        
    # Integer check
    try:
        return int(val_str)
    except ValueError:
        pass
        
    # Float check
    try:
        return float(val_str)
    except ValueError:
        pass
        
    # JSON check (list or dict)
    if (val_str.startswith("{") and val_str.endswith("}")) or (val_str.startswith("[") and val_str.endswith("]")):
        try:
            return json.loads(val_str)
        except ValueError:
            pass
            
    return val_str

def parse_tool_args(args_list):
    """
    Parses a sublist of arguments for a tool.
    Returns (tool_name, tool_input_dict).
    """
    if not args_list:
        raise ValueError("Empty command list")
        
    tool_name = args_list[0]
    tool_input = {}
    
    i = 1
    while i < len(args_list):
        arg = args_list[i]
        
        # Handle JSON string option
        if arg in ("-j", "--json"):
            if i + 1 >= len(args_list):
                raise ValueError("Missing JSON string after {} option".format(arg))
            try:
                json_data = json.loads(args_list[i + 1])
                if not isinstance(json_data, dict):
                    raise ValueError("JSON input must be a dictionary")
                tool_input.update(json_data)
            except Exception as e:
                raise ValueError("Invalid JSON string: {}".format(e))
            i += 2
            continue
            
        # Handle JSON file option
        if arg in ("-f", "--file"):
            if i + 1 >= len(args_list):
                raise ValueError("Missing file path after {} option".format(arg))
            file_path = args_list[i + 1]
            if not os.path.exists(file_path):
                raise ValueError("File not found: {}".format(file_path))
            try:
                with open(file_path, "r") as f:
                    json_data = json.load(f)
                if not isinstance(json_data, dict):
                    raise ValueError("JSON file content must be a dictionary")
                tool_input.update(json_data)
            except Exception as e:
                raise ValueError("Failed to parse JSON file: {}".format(e))
            i += 2
            continue
            
        # Handle key=value args
        if "=" in arg:
            key, val = arg.split("=", 1)
            tool_input[key.strip()] = parse_val(val.strip())
            i += 1
        else:
            raise ValueError("Invalid argument format: '{}'. Expected key=value or -j/-f options.".format(arg))
            
    return tool_name, tool_input

def execute_single_tool(tool_name, tool_input):
    """Executes a single tool on the bridge and prints results."""
    print("\n>>> EXECUTE: {}".format(tool_name))
    print("Args: {}".format(json.dumps(tool_input, indent=2)))
    print("-" * 60)
    
    payload = {
        "tool": tool_name,
        "input": tool_input
    }
    
    res = query_bridge("/execute/", method="POST", payload=payload)
    status = res.get("status", "unknown").upper()
    
    print("<<< RESPONSE (Status: {})".format(status))
    print("-" * 60)
    print(json.dumps(res, indent=2))
    print_separator()
    return res.get("status") == "success"

def handle_list():
    """Fetches and lists all registered tools from the bridge."""
    print("[*] Contacting Revit Bridge tool discovery...")
    res = query_bridge("/tools/", method="GET")
    
    if res.get("status") != "success":
        print("[!] Discovery failed: {}".format(res.get("message", "Unknown error")))
        sys.exit(1)
        
    tools = res.get("tools", [])
    print("\nDiscovered {} tool(s) registered in Revit:".format(len(tools)))
    print_separator("-")
    
    for tool in tools:
        print("  • \033[1m{}\033[0m: {}".format(tool.get("name"), tool.get("description", "No description")))
        params = tool.get("parameters", {}).get("properties", {})
        if params:
            print("    Parameters:")
            for p_name, p_info in params.items():
                req = " (Required)" if p_name in tool.get("parameters", {}).get("required", []) else ""
                print("      - {}: {}{} - {}".format(p_name, p_info.get("type"), req, p_info.get("description", "")))
        print_separator("-")

def handle_show(tool_name):
    """Shows full schema detail for a specific tool."""
    res = query_bridge("/tools/", method="GET")
    if res.get("status") != "success":
        print("[!] Discovery failed: {}".format(res.get("message", "Unknown error")))
        sys.exit(1)
        
    tools = res.get("tools", [])
    matched = [t for t in tools if t.get("name") == tool_name]
    
    if not matched:
        print("[!] Tool '{}' not found in bridge schemas.".format(tool_name))
        sys.exit(1)
        
    print(json.dumps(matched[0], indent=2))

def handle_run(args):
    """
    Parses and runs single or chained tool requests.
    e.g. run tool1 key=val --then tool2 key=val
    """
    # Segment by '--then'
    segments = []
    current_seg = []
    
    for arg in args:
        if arg == "--then":
            if current_seg:
                segments.append(current_seg)
                current_seg = []
            else:
                print("[!] Error: Empty command segment before '--then'")
                sys.exit(1)
        else:
            current_seg.append(arg)
            
    if current_seg:
        segments.append(current_seg)
        
    if not segments:
        print("[!] Error: No tools specified to run.")
        sys.exit(1)
        
    print("[*] Running {} tool(s)...".format(len(segments)))
    print_separator()
    
    for i, seg in enumerate(segments, 1):
        print("[Step {}/{}] Processing command: {}".format(i, len(segments), " ".join(seg)))
        try:
            tool_name, tool_input = parse_tool_args(seg)
        except ValueError as e:
            print("[!] Argument parsing error: {}".format(e))
            sys.exit(1)
            
        success = execute_single_tool(tool_name, tool_input)
        if not success:
            print("[!] Step failed. Halting chain.")
            sys.exit(1)
            
    print("\n[+] All tools executed successfully.")

def handle_batch(file_path):
    """Runs tool commands from a text or JSON file."""
    if not os.path.exists(file_path):
        print("[!] Batch file not found: {}".format(file_path))
        sys.exit(1)
        
    _, ext = os.path.splitext(file_path)
    
    if ext.lower() == ".json":
        # Parse JSON list
        try:
            with open(file_path, "r") as f:
                batch_data = json.load(f)
        except Exception as e:
            print("[!] Failed to parse JSON batch file: {}".format(e))
            sys.exit(1)
            
        if not isinstance(batch_data, list):
            print("[!] JSON batch file must contain a list of objects.")
            sys.exit(1)
            
        print("[*] Running JSON batch file ({} tools)...".format(len(batch_data)))
        print_separator()
        
        for i, item in enumerate(batch_data, 1):
            tool_name = item.get("tool")
            tool_input = item.get("input", {})
            if not tool_name:
                print("[!] Batch item {} missing 'tool' field.".format(i))
                sys.exit(1)
                
            print("[Step {}/{}] Running: {}".format(i, len(batch_data), tool_name))
            success = execute_single_tool(tool_name, tool_input)
            if not success:
                print("[!] Step failed. Halting batch.")
                sys.exit(1)
    else:
        # Parse text file line by line
        lines = []
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
                
        if not lines:
            print("[*] No commands found in batch file.")
            return
            
        print("[*] Running text batch file ({} tools)...".format(len(lines)))
        print_separator()
        
        for i, line in enumerate(lines, 1):
            print("[Step {}/{}] Line: {}".format(i, len(lines), line))
            try:
                args = shlex.split(line)
                tool_name, tool_input = parse_tool_args(args)
            except Exception as e:
                print("[!] Parsing error on line {}: {}".format(i, e))
                sys.exit(1)
                
            success = execute_single_tool(tool_name, tool_input)
            if not success:
                print("[!] Step failed. Halting batch.")
                sys.exit(1)
                
    print("\n[+] Batch executed successfully.")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    if cmd == "list":
        handle_list()
    elif cmd == "show":
        if len(sys.argv) < 3:
            print("[!] Error: Please specify tool name. Usage: python run_tool.py show <tool_name>")
            sys.exit(1)
        handle_show(sys.argv[2])
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("[!] Error: Please specify tool to run. Usage: python run_tool.py run <tool_name> [key=value ...]")
            sys.exit(1)
        handle_run(sys.argv[2:])
    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("[!] Error: Please specify batch file path. Usage: python run_tool.py batch <file_path>")
            sys.exit(1)
        handle_batch(sys.argv[2])
    else:
        print("[!] Unknown command: {}".format(cmd))
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()

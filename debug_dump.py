#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Revit AI Agent — Debug Session Dump Utility

Extracts the latest chat session, thoughts, tool calls, and results from agent.db
and writes a human-readable transcription file to backend/data/latest_run.md.
"""
import os
import sqlite3
import json
from datetime import datetime

# Absolute/relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "backend", "data", "agent.db")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "backend", "data", "latest_run.md")

def format_time(iso_str):
    try:
        # Simple string formatting for timestamps
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str

def main():
    if not os.path.exists(DB_PATH):
        print("[!] Database not found at: {}".format(DB_PATH))
        print("    Please ensure the backend has run at least once.")
        return

    print("[*] Reading database: {}".format(DB_PATH))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Get the latest updated session
        cursor.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 1;")
        session = cursor.fetchone()
        if not session:
            print("[-] No sessions found in the database.")
            return

        session_id = session["id"]
        session_name = session["name"]
        print("[+] Found latest session: '{}' (ID: {})".format(session_name, session_id))

        # 2. Get all messages for the latest session
        cursor.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC;",
            (session_id,)
        )
        messages = cursor.fetchall()
        print("[*] Retrieved {} message record(s).".format(len(messages)))

        # 3. Format message logs to Markdown
        md = []
        md.append("# Latest Chat Session Run")
        md.append("")
        md.append("* **Session Name:** `{}`".format(session_name))
        md.append("* **Session ID:** `{}`".format(session_id))
        md.append("* **Dumped At:** `{}`".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        md.append("")
        md.append("---")
        md.append("")

        for msg in messages:
            role = msg["role"].upper()
            created_at = format_time(msg["created_at"])
            
            md.append("## [{}] - {}".format(role, created_at))
            md.append("")

            # Render content based on role
            content = msg["content"]
            
            # Formatting thoughts if any
            if msg["agent_thoughts"]:
                try:
                    thoughts = json.loads(msg["agent_thoughts"])
                    if thoughts:
                        md.append("### 🧠 Agent Thoughts & Steps")
                        for thought in thoughts:
                            md.append("* {}".format(thought))
                        md.append("")
                except Exception:
                    pass

            if role == "USER":
                md.append("💬 **User:**")
                md.append(content)
                md.append("")
                if msg["images"]:
                    try:
                        imgs = json.loads(msg["images"])
                        if imgs:
                            md.append("📷 *Attached Images:*")
                            for idx, img in enumerate(imgs):
                                md.append("  - Attachment #{}".format(idx + 1))
                            md.append("")
                    except Exception:
                        pass

            elif role == "ASSISTANT":
                md.append("🤖 **Assistant:**")
                md.append(content)
                md.append("")
                
                # Check for tool calls made in this assistant turn
                if msg["tool_calls"]:
                    try:
                        calls = json.loads(msg["tool_calls"])
                        if calls:
                            md.append("🛠️ **Tool Call Requests:**")
                            for call in calls:
                                call_id = call.get("id", "N/A")
                                name = call.get("name", "N/A")
                                args = call.get("args", {})
                                md.append("- **Tool:** `{}` (Call ID: `{}`)".format(name, call_id))
                                md.append("  - **Parameters:**")
                                md.append("    ```json")
                                md.append(json.dumps(args, indent=4))
                                md.append("    ```")
                            md.append("")
                    except Exception:
                        pass

            elif role == "TOOL":
                tool_name = msg["tool_name"] or "unknown_tool"
                call_id = msg["tool_call_id"] or "N/A"
                approved = "Yes" if msg["approved"] else "No/N/A"
                
                md.append("🔧 **Tool Response:** `{}`".format(tool_name))
                md.append("* **Call ID Reference:** `{}`".format(call_id))
                md.append("* **Approved:** `{}`".format(approved))
                md.append("")
                md.append("#### Response Payload:")
                try:
                    res_json = json.loads(content)
                    md.append("```json")
                    md.append(json.dumps(res_json, indent=4))
                    md.append("```")
                except Exception:
                    md.append("```")
                    md.append(content)
                    md.append("```")
                md.append("")

            md.append("---")
            md.append("")

        # Write output file
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        print("[+] Diagnostic transcript successfully written to: {}".format(OUTPUT_PATH))

    except Exception as e:
        print("[!] Failure processing database dump: {}".format(e))
    finally:
        conn.close()

if __name__ == "__main__":
    main()

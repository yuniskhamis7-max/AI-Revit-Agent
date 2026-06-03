# -*- coding: utf-8 -*-
"""
Unit tests for the Revit AI Agent daemon modules.

Tests cover:
    - Bridge client: call_revit_bridge, load_tools_from_bridge
      - array, boolean, number schema type conversion
      - agent_instructions merging into description
    - Agent loop: single tool call, parallel calls, unregistered tool
      handling, fetch-then-action chaining, timing metadata in output
"""
import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os
import requests

# Ensure the daemon directory is on the path for config imports
daemon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if daemon_dir not in sys.path:
    sys.path.insert(0, daemon_dir)

from bridge.client import call_revit_bridge, load_tools_from_bridge
from agent.loop import run_agent_loop
from google.genai import types


class MockCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class MockResponse:
    def __init__(self, function_calls=None, text=""):
        self.function_calls = function_calls or []
        self.text = text


# =====================================================================
# BRIDGE CLIENT TESTS
# =====================================================================

class TestBridgeClient(unittest.TestCase):

    @patch("bridge.client.requests.post")
    def test_call_revit_bridge_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success", "element_id": "abc"}
        mock_post.return_value = mock_resp

        result = call_revit_bridge("create_grid", {"name": "Grid A"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["element_id"], "abc")

    @patch("bridge.client.requests.post")
    def test_call_revit_bridge_communication_failure(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Connection refused")

        result = call_revit_bridge("create_grid", {"name": "TestGrid"})
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["message"])

    @patch("bridge.client.requests.post")
    def test_call_revit_bridge_payload_format(self, mock_post):
        """Verify the POST payload uses 'tool' and 'input' keys."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success"}
        mock_post.return_value = mock_resp

        call_revit_bridge("fetch_levels", {"target_view_id": "view-abc"})

        call_args = mock_post.call_args
        sent_json = call_args[1]["json"]
        self.assertEqual(sent_json["tool"], "fetch_levels")
        self.assertEqual(sent_json["input"]["target_view_id"], "view-abc")

    @patch("bridge.client.requests.get")
    def test_load_tools_from_bridge_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "create_grid",
                    "description": "Creates a linear reference gridline.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Grid display name."}
                        },
                        "required": ["name"]
                    }
                },
                {
                    "name": "fetch_levels",
                    "description": "Fetches all levels.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        gemini_tools, tool_map = load_tools_from_bridge()

        self.assertEqual(len(gemini_tools), 2)
        self.assertEqual(gemini_tools[0].name, "create_grid")
        self.assertIn("create_grid", tool_map)
        self.assertIn("fetch_levels", tool_map)

    @patch("bridge.client.requests.get")
    def test_load_tools_array_property_has_items(self, mock_get):
        """
        BUG CHECK: array-type properties (e.g. propagate_to_views) must produce
        a Gemini Schema with items=Schema(type='string') so the model understands
        the element type. A bare Schema(type='array') gives the model no
        information about array contents, causing it to omit the argument.
        """
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "modify_grid",
                    "description": "Modifies a grid.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "grid_id": {"type": "string", "description": "Grid UniqueId."},
                            "propagate_to_views": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of view UniqueIds."
                            }
                        },
                        "required": ["grid_id"]
                    }
                }
            ]
        }

        gemini_tools, _ = load_tools_from_bridge()

        decl = gemini_tools[0]
        self.assertEqual(decl.name, "modify_grid")

        prop = decl.parameters.properties.get("propagate_to_views")
        self.assertIsNotNone(prop, "propagate_to_views should be present in Gemini schema")
        self.assertEqual(prop.type.value, "ARRAY")
        # The items should be populated so Gemini knows the element type
        self.assertIsNotNone(prop.items, "array property must have 'items' defined for Gemini")
        self.assertEqual(prop.items.type.value, "STRING")

    @patch("bridge.client.requests.get")
    def test_load_tools_boolean_and_number_types(self, mock_get):
        """
        BUG CHECK: boolean and number schema types must be preserved exactly.
        The old flat Schema() builder defaulted everything to 'string'.
        """
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "create_level",
                    "description": "Creates a level.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name"},
                            "elevation": {"type": "number", "description": "Height in feet"},
                            "is_structural": {"type": "boolean", "description": "Structural flag"},
                            "create_floor_plan": {"type": "boolean", "description": "Auto-create floor plan"},
                        },
                        "required": ["name", "elevation"]
                    }
                }
            ]
        }

        gemini_tools, _ = load_tools_from_bridge()
        decl = gemini_tools[0]

        self.assertEqual(decl.parameters.properties["name"].type.value, "STRING")
        self.assertEqual(decl.parameters.properties["elevation"].type.value, "NUMBER")
        self.assertEqual(decl.parameters.properties["is_structural"].type.value, "BOOLEAN")
        self.assertEqual(decl.parameters.properties["create_floor_plan"].type.value, "BOOLEAN")

    @patch("bridge.client.requests.get")
    def test_load_tools_agent_instructions_merged(self, mock_get):
        """agent_instructions must appear in the full_description sent to Gemini."""
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "fetch_grids",
                    "description": "Fetches all grids.",
                    "agent_instructions": "Call before create_grid to check names.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            ]
        }

        gemini_tools, _ = load_tools_from_bridge()
        decl = gemini_tools[0]
        self.assertIn("BEFORE CALLING", decl.description)
        self.assertIn("Call before create_grid", decl.description)

    @patch("bridge.client.requests.get")
    def test_load_tools_dispatcher_calls_bridge(self, mock_get):
        """Verify that the dispatchers built by load_tools actually POST to the bridge."""
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "create_grid",
                    "description": "Creates a grid.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "description": "Name"}},
                        "required": ["name"]
                    }
                }
            ]
        }
        mock_get.return_value = mock_get_resp

        _, tool_map = load_tools_from_bridge()

        with patch("bridge.client.requests.post") as mock_post:
            mock_post_resp = MagicMock()
            mock_post_resp.json.return_value = {"status": "success", "element_id": "123"}
            mock_post.return_value = mock_post_resp

            result = tool_map["create_grid"](name="TestGrid")
            self.assertEqual(result, {"status": "success", "element_id": "123"})

    @patch("bridge.client.requests.get")
    def test_load_tools_fetch_tool_no_args(self, mock_get):
        """Verify fetch tools work with no arguments."""
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = {
            "status": "success",
            "tools": [
                {
                    "name": "fetch_levels",
                    "description": "Fetches all levels.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            ]
        }
        mock_get.return_value = mock_get_resp

        _, tool_map = load_tools_from_bridge()

        with patch("bridge.client.requests.post") as mock_post:
            mock_post_resp = MagicMock()
            mock_post_resp.json.return_value = {
                "status": "success",
                "levels": [{"name": "Level 1", "id": "abc", "elevation": 0.0}]
            }
            mock_post.return_value = mock_post_resp

            result = tool_map["fetch_levels"]()
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["levels"]), 1)

    @patch("bridge.client.requests.get")
    def test_load_tools_all_new_tools_registered(self, mock_get):
        """
        Verify that all 6 new/enhanced tools appear in the tool registry
        returned by the discovery endpoint in the expected shape.
        """
        expected_names = {
            "fetch_project_info", "fetch_levels", "fetch_grids",
            "fetch_families", "fetch_sheets",
            "place_family", "create_grid", "modify_grid",
            "create_level", "modify_level", "create_sheet"
        }
        tools_payload = [
            {"name": n, "description": "desc", "parameters": {"type": "object", "properties": {}, "required": []}}
            for n in expected_names
        ]
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.return_value = {"status": "success", "tools": tools_payload}

        gemini_tools, tool_map = load_tools_from_bridge()

        registered = {t.name for t in gemini_tools}
        self.assertEqual(registered, expected_names)
        self.assertEqual(set(tool_map.keys()), expected_names)


# =====================================================================
# AGENT LOOP TESTS
# =====================================================================

class TestAgentLoop(unittest.TestCase):

    @patch("agent.loop.client")
    def test_run_agent_loop_single_tool_call(self, mock_client):
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        first_resp = MockResponse(
            function_calls=[MockCall("create_grid", {"name": "AlphaGrid"})]
        )
        second_resp = MockResponse(
            text="Successfully created the grid AlphaGrid."
        )
        mock_chat.send_message.side_effect = [first_resp, second_resp]

        mock_tool_fn = MagicMock(return_value={"status": "success", "element_id": "grid-123"})
        tool_map = {"create_grid": mock_tool_fn}
        gemini_tools = [types.FunctionDeclaration(
            name="create_grid", description="Grid",
            parameters=types.Schema(type="object")
        )]

        result = run_agent_loop(
            user_prompt="Create grid named AlphaGrid",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "Successfully created the grid AlphaGrid.")
        mock_tool_fn.assert_called_once_with(name="AlphaGrid")
        self.assertEqual(mock_chat.send_message.call_count, 2)

    @patch("agent.loop.client")
    def test_run_agent_loop_parallel_tool_calls(self, mock_client):
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        first_resp = MockResponse(
            function_calls=[
                MockCall("create_grid", {"name": "GridA"}),
                MockCall("create_grid", {"name": "GridB"})
            ]
        )
        second_resp = MockResponse(
            text="Successfully created GridA and GridB."
        )
        mock_chat.send_message.side_effect = [first_resp, second_resp]

        mock_tool_fn = MagicMock(side_effect=[
            {"status": "success", "element_id": "grid-a"},
            {"status": "success", "element_id": "grid-b"}
        ])
        tool_map = {"create_grid": mock_tool_fn}
        gemini_tools = [types.FunctionDeclaration(
            name="create_grid", description="Grid",
            parameters=types.Schema(type="object")
        )]

        result = run_agent_loop(
            user_prompt="Create GridA and GridB",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "Successfully created GridA and GridB.")
        self.assertEqual(mock_tool_fn.call_count, 2)
        self.assertEqual(mock_chat.send_message.call_count, 2)

        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        self.assertIsInstance(sent_parts, list)
        self.assertEqual(len(sent_parts), 2)

    @patch("agent.loop.client")
    def test_run_agent_loop_unregistered_tool_call(self, mock_client):
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        first_resp = MockResponse(
            function_calls=[MockCall("unknown_action", {"param": "val"})]
        )
        second_resp = MockResponse(
            text="Sorry, I encountered an unsupported action."
        )
        mock_chat.send_message.side_effect = [first_resp, second_resp]

        tool_map = {"create_grid": MagicMock()}
        gemini_tools = []

        result = run_agent_loop(
            user_prompt="Do something unknown",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "Sorry, I encountered an unsupported action.")
        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        self.assertEqual(len(sent_parts), 1)
        self.assertIn("error", sent_parts[0].function_response.response["result"]["status"])

    @patch("agent.loop.client")
    def test_run_agent_loop_fetch_then_action(self, mock_client):
        """
        Verify the agent can chain a fetch call followed by an action call
        across multiple conversation turns.
        """
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        # Turn 1: Agent calls fetch_levels
        resp_1 = MockResponse(
            function_calls=[MockCall("fetch_levels", {})]
        )
        # Turn 2: Agent calls create_grid using fetched level data
        resp_2 = MockResponse(
            function_calls=[MockCall("create_grid", {"name": "Grid A", "start_x": 0, "start_y": 0, "end_x": 100, "end_y": 0})]
        )
        # Turn 3: Final text response
        resp_3 = MockResponse(text="Created Grid A spanning 100 feet.")

        mock_chat.send_message.side_effect = [resp_1, resp_2, resp_3]

        mock_fetch_levels = MagicMock(return_value={
            "status": "success",
            "levels": [{"name": "Level 1", "id": "lvl-1", "elevation": 0.0}]
        })
        mock_create_grid = MagicMock(return_value={
            "status": "success",
            "element_id": "grid-1",
            "message": "Grid created."
        })

        tool_map = {
            "fetch_levels": mock_fetch_levels,
            "create_grid": mock_create_grid
        }
        gemini_tools = [
            types.FunctionDeclaration(name="fetch_levels", description="Levels", parameters=types.Schema(type="object")),
            types.FunctionDeclaration(name="create_grid", description="Grid", parameters=types.Schema(type="object"))
        ]

        result = run_agent_loop(
            user_prompt="Create a grid spanning 100 feet",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "Created Grid A spanning 100 feet.")
        mock_fetch_levels.assert_called_once()
        mock_create_grid.assert_called_once()
        self.assertEqual(mock_chat.send_message.call_count, 3)

    @patch("agent.loop.client")
    def test_run_agent_loop_returns_timing_metadata(self, mock_client):
        """
        BUG CHECK: The loop should emit per-tool timing so we can measure
        agent performance. Verify run_agent_loop returns a dict with
        'response' and 'tool_timings' keys when timing is enabled.
        """
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        resp_1 = MockResponse(
            function_calls=[MockCall("fetch_grids", {})]
        )
        resp_2 = MockResponse(text="Done.")
        mock_chat.send_message.side_effect = [resp_1, resp_2]

        mock_fetch_grids = MagicMock(return_value={"status": "success", "grids": []})
        tool_map = {"fetch_grids": mock_fetch_grids}
        gemini_tools = [types.FunctionDeclaration(
            name="fetch_grids", description="Grids",
            parameters=types.Schema(type="object")
        )]

        result = run_agent_loop(
            user_prompt="List all grids",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        # run_agent_loop always returns a structured dict
        self.assertIsInstance(result, dict, "run_agent_loop must return a dict")
        self.assertIn("response", result)
        self.assertIn("tool_timings", result)
        self.assertIn("total_ms", result)

        # Verify timing was captured for fetch_grids
        self.assertEqual(len(result["tool_timings"]), 1)
        timing = result["tool_timings"][0]
        self.assertEqual(timing["tool"], "fetch_grids")
        self.assertIn("duration_ms", timing)
        self.assertGreaterEqual(timing["duration_ms"], 0.0)

        # Final text is accessible
        self.assertEqual(result["response"], "Done.")


    @patch("agent.loop.client")
    def test_run_agent_loop_mixed_parallel_success_and_error(self, mock_client):
        """
        BUG CHECK: When two tools are called in parallel and one returns an
        error dict, the loop must still send both responses back to Gemini
        (not crash on the error). The agent then handles the partial result.
        """
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        resp_1 = MockResponse(function_calls=[
            MockCall("create_grid", {"name": "Grid X"}),
            MockCall("create_level", {"name": "Level X", "elevation": 10.0})
        ])
        resp_2 = MockResponse(text="Partial success — level failed but grid was created.")
        mock_chat.send_message.side_effect = [resp_1, resp_2]

        tool_map = {
            "create_grid":  MagicMock(return_value={"status": "success", "element_id": "g1"}),
            "create_level": MagicMock(return_value={"status": "error", "message": "Name conflict"})
        }
        gemini_tools = [
            types.FunctionDeclaration(name="create_grid", description="Grid", parameters=types.Schema(type="object")),
            types.FunctionDeclaration(name="create_level", description="Level", parameters=types.Schema(type="object"))
        ]

        # Must not raise; must return the final text
        result = run_agent_loop(
            user_prompt="Create Grid X and Level X",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertIsInstance(result, dict)
        response_text = result["response"]
        self.assertIn("Partial success", response_text)

        # Both tool functions were called
        tool_map["create_grid"].assert_called_once()
        tool_map["create_level"].assert_called_once()

        # Both responses were sent back to Gemini in one batch
        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        self.assertEqual(len(sent_parts), 2)


if __name__ == "__main__":
    unittest.main()

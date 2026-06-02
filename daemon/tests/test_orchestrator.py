# -*- coding: utf-8 -*-
"""
Unit tests for the Revit AI Agent daemon modules.

Tests cover:
    - Bridge client: call_revit_bridge, load_tools_from_bridge
    - Agent loop: single tool call, parallel calls, unregistered tool handling
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

        final_text = run_agent_loop(
            user_prompt="Create grid named AlphaGrid",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertEqual(final_text, "Successfully created the grid AlphaGrid.")
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

        final_text = run_agent_loop(
            user_prompt="Create GridA and GridB",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertEqual(final_text, "Successfully created GridA and GridB.")
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

        final_text = run_agent_loop(
            user_prompt="Do something unknown",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertEqual(final_text, "Sorry, I encountered an unsupported action.")
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

        final_text = run_agent_loop(
            user_prompt="Create a grid spanning 100 feet",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        self.assertEqual(final_text, "Created Grid A spanning 100 feet.")
        mock_fetch_levels.assert_called_once()
        mock_create_grid.assert_called_once()
        self.assertEqual(mock_chat.send_message.call_count, 3)


if __name__ == "__main__":
    unittest.main()

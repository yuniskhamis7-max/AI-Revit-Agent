# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
import json
import requests

# Import the code to test
# To prevent real client initialization on import if it executes immediately,
# we mock genai.Client before importing or handle it in setup.
import orchestrator
from google.genai import types

class MockCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

class MockResponse:
    def __init__(self, function_calls=None, text=""):
        self.function_calls = function_calls or []
        self.text = text

class TestOrchestrator(unittest.TestCase):

    @patch("orchestrator.requests.get")
    def test_load_tools_from_bridge_success(self, mock_get):
        # Mock successful GET /tools/ endpoint
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
                }
            ]
        }
        mock_get.return_value = mock_response

        # Execute
        gemini_tools, tool_map = orchestrator.load_tools_from_bridge()

        # Assertions
        self.assertEqual(len(gemini_tools), 1)
        self.assertEqual(gemini_tools[0].name, "create_grid")
        self.assertEqual(gemini_tools[0].description, "Creates a linear reference gridline.")
        self.assertIn("create_grid", tool_map)

        # Test dynamic dispatcher calls requests.post
        with patch("orchestrator.requests.post") as mock_post:
            mock_post_resp = MagicMock()
            mock_post_resp.json.return_value = {"status": "success", "element_id": "123"}
            mock_post.return_value = mock_post_resp

            dispatcher_fn = tool_map["create_grid"]
            res = dispatcher_fn(name="TestGrid")

            self.assertEqual(res, {"status": "success", "element_id": "123"})
            mock_post.assert_called_once_with(
                orchestrator.REVIT_BRIDGE_URL,
                json={"action": "create_grid", "parameters": {"name": "TestGrid"}},
                timeout=30
            )

    @patch("orchestrator.requests.post")
    def test_call_revit_bridge_communication_failure(self, mock_post):
        # Mock requests exception
        mock_post.side_effect = requests.exceptions.RequestException("Connection refused")

        result = orchestrator.call_revit_bridge("create_grid", {"name": "TestGrid"})
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["message"])

    @patch("orchestrator.client")
    def test_run_agent_loop_single_tool_call(self, mock_client):
        # Setup mocks
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        # First chat response returns a function call
        first_resp = MockResponse(
            function_calls=[MockCall("create_grid", {"name": "AlphaGrid"})]
        )
        # Second response (after function response is sent) returns text
        second_resp = MockResponse(
            text="Successfully created the grid AlphaGrid."
        )
        mock_chat.send_message.side_effect = [first_resp, second_resp]

        # Mock tool map
        mock_tool_fn = MagicMock(return_value={"status": "success", "element_id": "grid-123"})
        tool_map = {"create_grid": mock_tool_fn}
        gemini_tools = [types.FunctionDeclaration(name="create_grid", description="Grid", parameters=types.Schema(type="object"))]

        # Execute
        final_text = orchestrator.run_agent_loop(
            user_prompt="Create grid named AlphaGrid",
            project_context="{}",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        # Assertions
        self.assertEqual(final_text, "Successfully created the grid AlphaGrid.")
        mock_tool_fn.assert_called_once_with(name="AlphaGrid")
        
        # Verify chat interactions:
        # 1. Composed prompt sent
        # 2. Tool response sent
        self.assertEqual(mock_chat.send_message.call_count, 2)
        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        # Check that it sent a single part with correct structure
        self.assertIsInstance(sent_parts, list)
        self.assertEqual(len(sent_parts), 1)
        self.assertEqual(sent_parts[0].function_response.name, "create_grid")
        self.assertEqual(sent_parts[0].function_response.response, {"result": {"status": "success", "element_id": "grid-123"}})

    @patch("orchestrator.client")
    def test_run_agent_loop_parallel_tool_calls(self, mock_client):
        # Setup mocks
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        # First chat response returns two parallel tool calls
        first_resp = MockResponse(
            function_calls=[
                MockCall("create_grid", {"name": "GridA"}),
                MockCall("create_grid", {"name": "GridB"})
            ]
        )
        # Second response returns text
        second_resp = MockResponse(
            text="Successfully created GridA and GridB."
        )
        mock_chat.send_message.side_effect = [first_resp, second_resp]

        # Mock tool map
        mock_tool_fn = MagicMock(side_effect=[
            {"status": "success", "element_id": "grid-a"},
            {"status": "success", "element_id": "grid-b"}
        ])
        tool_map = {"create_grid": mock_tool_fn}
        gemini_tools = [types.FunctionDeclaration(name="create_grid", description="Grid", parameters=types.Schema(type="object"))]

        # Execute
        final_text = orchestrator.run_agent_loop(
            user_prompt="Create GridA and GridB",
            project_context="{}",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        # Assertions
        self.assertEqual(final_text, "Successfully created GridA and GridB.")
        self.assertEqual(mock_tool_fn.call_count, 2)
        
        # Verify chat interactions:
        # Exactly 2 send_message calls total (initial prompt, and then BOTH responses sent at once)
        self.assertEqual(mock_chat.send_message.call_count, 2)
        
        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        self.assertIsInstance(sent_parts, list)
        self.assertEqual(len(sent_parts), 2)
        self.assertEqual(sent_parts[0].function_response.name, "create_grid")
        self.assertEqual(sent_parts[0].function_response.response, {"result": {"status": "success", "element_id": "grid-a"}})
        self.assertEqual(sent_parts[1].function_response.name, "create_grid")
        self.assertEqual(sent_parts[1].function_response.response, {"result": {"status": "success", "element_id": "grid-b"}})

    @patch("orchestrator.client")
    def test_run_agent_loop_unregistered_tool_call(self, mock_client):
        # Setup mocks
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

        # Execute
        final_text = orchestrator.run_agent_loop(
            user_prompt="Do something unknown",
            project_context="{}",
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )

        # Assertions
        self.assertEqual(final_text, "Sorry, I encountered an unsupported action.")
        self.assertEqual(mock_chat.send_message.call_count, 2)
        
        sent_parts = mock_chat.send_message.call_args_list[1][0][0]
        self.assertEqual(len(sent_parts), 1)
        self.assertEqual(sent_parts[0].function_response.name, "unknown_action")
        self.assertIn("error", sent_parts[0].function_response.response["result"]["status"])

if __name__ == "__main__":
    unittest.main()

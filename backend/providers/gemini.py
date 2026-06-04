# -*- coding: utf-8 -*-
"""
Google Gemini Provider Adapter.

Wraps the google-genai SDK and normalises its response stream into the
provider-agnostic event format consumed by the agent service.

Preserves all the proven patterns from the original daemon/agent/loop.py:
  - Rate-limit retry with retryDelay parsing
  - Temperature=0 for deterministic tool calling
  - Multi-turn function response batching
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from providers.base import AIProvider, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5

# Ordered list of models surfaced in the frontend dropdown (fallback if API unavailable)
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
]


def fetch_gemini_models(api_key: str) -> list[str]:
    """
    Dynamically fetch available Gemini models from the Google API.
    Falls back to the static GEMINI_MODELS list on failure.
    """
    try:
        client = genai.Client(api_key=api_key)
        models = []
        for m in client.models.list():
            name = m.name or ""
            # Only include generative models (not embeddings, etc.)
            if name and "gemini" in name.lower() and "generateContent" in (m.supported_actions or []):
                # Strip the "models/" prefix if present
                clean_name = name.replace("models/", "") if name.startswith("models/") else name
                models.append(clean_name)
        if models:
            return models
    except Exception as exc:
        logger.warning("Failed to fetch Gemini models from API: %s. Using static list.", exc)
    return list(GEMINI_MODELS)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_retry_delay(error: Exception) -> float:
    try:
        match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([\d.]+)s", str(error))
        if match:
            return float(match.group(1))
    except Exception:
        pass
    return 5.0


def _build_function_declarations(tool_schemas: list[dict]) -> list[types.FunctionDeclaration]:
    """Converts raw bridge tool schemas into Gemini FunctionDeclaration objects."""

    def _prop(prop_def: dict) -> types.Schema:
        prop_type = prop_def.get("type", "string").upper()
        prop_desc = prop_def.get("description", "")
        if prop_type == "ARRAY":
            items_def = prop_def.get("items", {})
            items_schema = _prop(items_def) if items_def else types.Schema(type="STRING")
            return types.Schema(type="ARRAY", description=prop_desc, items=items_schema)
        return types.Schema(type=prop_type, description=prop_desc)

    declarations = []
    for schema in tool_schemas:
        name = schema["name"]
        description = schema["description"]
        parameters = schema.get("parameters", {})
        agent_instructions = schema.get("agent_instructions", "")
        if agent_instructions:
            description = description + "\n\nBEFORE CALLING: " + agent_instructions

        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=types.Schema(
                    type=parameters.get("type", "object").upper(),
                    properties={
                        k: _prop(v)
                        for k, v in parameters.get("properties", {}).items()
                    },
                    required=parameters.get("required", []),
                ),
            )
        )
    return declarations


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Provider
# ─────────────────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    name = "gemini"
    available_models = GEMINI_MODELS

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("AI"))

    async def stream_agent_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Runs one Gemini model inference turn.

        The Gemini SDK is synchronous; we run it in a thread-pool executor
        to avoid blocking the async event loop.

        Yields provider-agnostic event dicts (text_delta, tool_call, done).
        """
        declarations = _build_function_declarations(tool_schemas)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=declarations)] if declarations else [],
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=2048),
        )

        # Convert provider-agnostic messages to Gemini Content objects
        gemini_contents = _to_gemini_contents(messages)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._send_with_retry(gemini_contents, config),
        )

        # Extract thinking/reasoning parts and thought signatures (Gemini 2.5 models)
        thought_signatures: dict[str, str] = {}  # Maps tool name -> thought_signature
        try:
            candidate = response.candidates[0] if response.candidates else None
            if candidate and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    # Capture thinking text for frontend display
                    if getattr(part, 'thought', False) and hasattr(part, 'text') and part.text:
                        yield {"type": "thinking_delta", "content": part.text}
                    # Capture thought_signature from function call parts (required for multi-turn)
                    sig = getattr(part, 'thought_signature', None)
                    if sig and hasattr(part, 'function_call') and part.function_call:
                        thought_signatures[part.function_call.name] = sig
        except (IndexError, AttributeError):
            pass

        # Yield text delta if present (ensure it's a plain string)
        text = getattr(response, "text", None) or ""
        if text and isinstance(text, str):
            yield {"type": "text_delta", "content": text}
        elif text:
            # SDK returned a non-string text (e.g. structured Part) — stringify
            yield {"type": "text_delta", "content": str(text)}

        # Yield tool calls if present (include thought_signature for multi-turn history)
        for fc in (response.function_calls or []):
            yield {
                "type": "tool_call",
                "id": fc.name,  # Gemini doesn't return a unique call ID; use name
                "name": fc.name,
                "args": dict(fc.args),
                "thought_signature": thought_signatures.get(fc.name),
            }

        yield {"type": "done"}

    def _send_with_retry(self, contents, config):
        """Synchronous Gemini call with 429 retry logic (runs in executor)."""
        # Use generate_content (stateless) to stay compatible with our own
        # multi-turn loop managed by agent.py
        for attempt in range(_MAX_RETRIES):
            try:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            except genai_errors.ClientError as exc:
                if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
                    raise
                wait = min(_extract_retry_delay(exc) + 1.0, 60.0)
                logger.warning("Gemini rate-limit hit. Retrying in %.1fs (attempt %d/%d).", wait, attempt + 1, _MAX_RETRIES)
                time.sleep(wait)

        raise RuntimeError(f"Gemini API rate limit persisted after {_MAX_RETRIES} retries.")


# ─────────────────────────────────────────────────────────────────────────────
# Message conversion
# ─────────────────────────────────────────────────────────────────────────────

def _to_gemini_contents(messages: list[dict]) -> list:
    """
    Converts the provider-agnostic message list to Gemini Content objects.

    Supported roles: 'user', 'assistant', 'tool'
    """
    contents = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=content)]))

        elif role == "assistant":
            parts = []
            if content:
                parts.append(types.Part.from_text(text=content))
            # Reconstruct tool_use parts from stored tool_calls (preserve thought_signature)
            for tc in msg.get("tool_calls", []):
                fc_part = types.Part.from_function_call(
                    name=tc["name"],
                    args=tc["args"],
                )
                # Restore thought_signature if present (required by Gemini 2.5 with thinking)
                sig = tc.get("thought_signature")
                if sig:
                    fc_part.thought_signature = sig
                parts.append(fc_part)
            if parts:
                contents.append(types.Content(role="model", parts=parts))

        elif role == "tool":
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=msg.get("name", "unknown"),
                            response={"result": json.loads(content) if isinstance(content, str) else content},
                        )
                    ],
                )
            )

    return contents

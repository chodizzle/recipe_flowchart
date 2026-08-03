"""Google (Gemini) provider: forced function-call extraction, text or image input."""

from __future__ import annotations

import time
from pathlib import Path

from google import genai
from google.genai import types

from .base import (
    EXTRACTION_INSTRUCTIONS,
    RECIPE_GRAPH_SCHEMA,
    SEED,
    TEMPERATURE,
    ExtractionResult,
    Provider,
    validate_graph,
)

# USD per million tokens: (input, output). Standard listed rates, Aug 2026.
# Gemini 2.5 is no longer available to new API keys; 3.x has no stable (non-preview) pro
# tier yet, so flash-lite/flash are the two stable tiers used here.
PRICING_PER_MTOK = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
}

_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="record_recipe_graph",
            description="Record the recipe's ingredient/operation dependency graph.",
            parametersJsonSchema=RECIPE_GRAPH_SCHEMA,
        )
    ]
)


class GoogleProvider(Provider):
    name = "google"

    def __init__(self, api_key: str | None = None):
        self._client = genai.Client(api_key=api_key)

    def _call(self, model: str, contents: list[types.Part]) -> ExtractionResult:
        start = time.perf_counter()
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=EXTRACTION_INSTRUCTIONS,
                temperature=TEMPERATURE,
                seed=SEED,
                tools=[_TOOL],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY,
                        allowed_function_names=["record_recipe_graph"],
                    )
                ),
            ),
        )
        latency = time.perf_counter() - start

        call = response.candidates[0].content.parts[0].function_call
        data = call.args
        nodes = list(data.get("nodes", []))
        validate_graph(nodes)

        usage = response.usage_metadata
        in_rate, out_rate = PRICING_PER_MTOK.get(model, (0.0, 0.0))
        cost = (usage.prompt_token_count / 1e6) * in_rate + (
            usage.candidates_token_count / 1e6
        ) * out_rate

        return ExtractionResult(
            provider=self.name,
            model=model,
            title=data.get("title", ""),
            nodes=nodes,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
            latency_s=latency,
            estimated_cost_usd=cost,
        )

    def extract_from_text(self, text: str, model: str) -> ExtractionResult:
        return self._call(model, [types.Part.from_text(text=text)])

    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult:
        media_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        contents = [
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type=media_type),
            types.Part.from_text(text="Extract the recipe from this photo."),
        ]
        return self._call(model, contents)

"""OpenAI provider: forced function-call extraction, text or image input."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from openai import OpenAI

from .base import EXTRACTION_INSTRUCTIONS, RECIPE_STEPS_SCHEMA, ExtractionResult, Provider

# USD per million tokens: (input, output). Standard listed rates, Aug 2026.
PRICING_PER_MTOK = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

_TOOL = {
    "type": "function",
    "function": {
        "name": "record_recipe_steps",
        "description": "Record the recipe's structured step breakdown.",
        "parameters": RECIPE_STEPS_SCHEMA,
    },
}


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str | None = None):
        self._client = OpenAI(api_key=api_key)

    def _call(self, model: str, user_content: str | list[dict]) -> ExtractionResult:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_INSTRUCTIONS},
                {"role": "user", "content": user_content},
            ],
            tools=[_TOOL],
            tool_choice={"type": "function", "function": {"name": "record_recipe_steps"}},
        )
        latency = time.perf_counter() - start

        tool_call = response.choices[0].message.tool_calls[0]
        data = json.loads(tool_call.function.arguments)

        in_rate, out_rate = PRICING_PER_MTOK.get(model, (0.0, 0.0))
        cost = (response.usage.prompt_tokens / 1e6) * in_rate + (
            response.usage.completion_tokens / 1e6
        ) * out_rate

        return ExtractionResult(
            provider=self.name,
            model=model,
            title=data.get("title", ""),
            steps=data.get("steps", []),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            latency_s=latency,
            estimated_cost_usd=cost,
        )

    def extract_from_text(self, text: str, model: str) -> ExtractionResult:
        return self._call(model, text)

    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult:
        media_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        content = [
            {"type": "text", "text": "Extract the recipe from this photo."},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
        ]
        return self._call(model, content)

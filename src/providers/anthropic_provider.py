"""Anthropic provider: forced tool-use extraction, text or image input."""

from __future__ import annotations

import base64
import time
from pathlib import Path

import anthropic

from .base import (
    EXTRACTION_INSTRUCTIONS,
    RECIPE_GRAPH_SCHEMA,
    TEMPERATURE,
    ExtractionResult,
    Provider,
    validate_graph,
)

# USD per million tokens: (input, output). Standard listed rates.
PRICING_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}

_TOOL = {
    "name": "record_recipe_graph",
    "description": "Record the recipe's ingredient/operation dependency graph.",
    "input_schema": RECIPE_GRAPH_SCHEMA,
}


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None):
        self._client = anthropic.Anthropic(api_key=api_key)

    def _call(self, model: str, content: str | list[dict]) -> ExtractionResult:
        kwargs = dict(
            model=model,
            max_tokens=4096,
            system=EXTRACTION_INSTRUCTIONS,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_recipe_graph"},
            messages=[{"role": "user", "content": content}],
        )
        start = time.perf_counter()
        try:
            # Not every current model accepts an explicit temperature (e.g. claude-sonnet-5
            # 400s with "temperature is deprecated for this model") -- fall back without it.
            response = self._client.messages.create(temperature=TEMPERATURE, **kwargs)
        except anthropic.BadRequestError as e:
            if "temperature" not in str(e):
                raise
            response = self._client.messages.create(**kwargs)
        latency = time.perf_counter() - start

        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input
        nodes = data.get("nodes", [])
        validate_graph(nodes)

        in_rate, out_rate = PRICING_PER_MTOK.get(model, (0.0, 0.0))
        cost = (response.usage.input_tokens / 1e6) * in_rate + (
            response.usage.output_tokens / 1e6
        ) * out_rate

        return ExtractionResult(
            provider=self.name,
            model=model,
            title=data.get("title", ""),
            nodes=nodes,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=latency,
            estimated_cost_usd=cost,
        )

    def extract_from_text(self, text: str, model: str) -> ExtractionResult:
        return self._call(model, text)

    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult:
        media_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            },
            {"type": "text", "text": "Extract the recipe from this photo."},
        ]
        return self._call(model, content)

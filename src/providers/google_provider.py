"""Google (Gemini) provider -- stubbed until a GOOGLE_API_KEY is available.

Get a free-tier key from https://aistudio.google.com/apikey, drop it into
.env as GOOGLE_API_KEY, then implement extract_from_text/extract_from_image
against the google-genai SDK (mirrors the Anthropic/OpenAI providers: forced
function-call output against RECIPE_STEPS_SCHEMA, image bytes as inline_data).
"""

from __future__ import annotations

from pathlib import Path

from .base import ExtractionResult, Provider

# USD per million tokens: (input, output) -- fill in once wired up.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {}


class GoogleProvider(Provider):
    name = "google"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def extract_from_text(self, text: str, model: str) -> ExtractionResult:
        raise NotImplementedError("Google provider not wired up yet -- see module docstring.")

    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult:
        raise NotImplementedError("Google provider not wired up yet -- see module docstring.")

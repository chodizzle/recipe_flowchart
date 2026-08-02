"""Provider-agnostic dispatch: recipe (text or image) -> structured steps + usage stats."""

from __future__ import annotations

from pathlib import Path

from providers.anthropic_provider import AnthropicProvider
from providers.base import ExtractionResult
from providers.google_provider import GoogleProvider
from providers.openai_provider import OpenAIProvider

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def parse_recipe(source: str | Path, provider: str, model: str) -> ExtractionResult:
    """Extract structured steps from a recipe.

    `source` is either a path to a recipe file (image or text) or raw recipe text.
    """
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Choose from {sorted(_PROVIDERS)}.")

    client = _PROVIDERS[provider]()

    path = source if isinstance(source, Path) else _as_existing_path(source)
    if path is not None and path.exists():
        if path.suffix.lower() in IMAGE_SUFFIXES:
            return client.extract_from_image(path, model)
        return client.extract_from_text(path.read_text(encoding="utf-8"), model)

    return client.extract_from_text(str(source), model)


def _as_existing_path(source: str) -> Path | None:
    if len(source) < 260 and "\n" not in source:
        candidate = Path(source)
        if candidate.exists():
            return candidate
    return None

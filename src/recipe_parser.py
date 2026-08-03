"""Provider-agnostic dispatch: recipe (text or image) -> structured graph + usage stats.

Extraction calls are real money, so results are cached to disk, keyed by everything that
could change the output: provider, model, the recipe's own bytes, and the prompt/schema/
sampling settings. Touch any of those and the cache key changes, so a schema or prompt
edit can't silently serve a stale extraction -- it just costs one more real call.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from providers.anthropic_provider import AnthropicProvider
from providers.base import EXTRACTION_INSTRUCTIONS, RECIPE_GRAPH_SCHEMA, SEED, TEMPERATURE, ExtractionResult
from providers.google_provider import GoogleProvider
from providers.openai_provider import OpenAIProvider

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "extractions"


def parse_recipe(source: str | Path, provider: str, model: str, use_cache: bool = True) -> ExtractionResult:
    """Extract a structured node graph from a recipe.

    `source` is either a path to a recipe file (image or text) or raw recipe text.
    `use_cache=False` forces a real API call (e.g. `--fresh`), but the result is always
    written back to the cache afterward -- "skip the cache" and "don't populate it for
    next time" are different things, and only the former is what `--fresh` should mean.
    """
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}. Choose from {sorted(_PROVIDERS)}.")

    path = source if isinstance(source, Path) else _as_existing_path(source)
    content = path.read_bytes() if path is not None and path.exists() else str(source).encode("utf-8")
    cache_path = _cache_path(provider, model, content)

    if use_cache and cache_path.exists():
        return ExtractionResult(**json.loads(cache_path.read_text(encoding="utf-8")))

    client = _PROVIDERS[provider]()
    if path is not None and path.exists():
        if path.suffix.lower() in IMAGE_SUFFIXES:
            result = client.extract_from_image(path, model)
        else:
            result = client.extract_from_text(path.read_text(encoding="utf-8"), model)
    else:
        result = client.extract_from_text(str(source), model)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def is_cached(source: str | Path, provider: str, model: str) -> bool:
    path = source if isinstance(source, Path) else _as_existing_path(source)
    content = path.read_bytes() if path is not None and path.exists() else str(source).encode("utf-8")
    return _cache_path(provider, model, content).exists()


def _cache_path(provider: str, model: str, content: bytes) -> Path:
    h = hashlib.sha256()
    for part in (provider, model, EXTRACTION_INSTRUCTIONS, json.dumps(RECIPE_GRAPH_SCHEMA, sort_keys=True), str(TEMPERATURE), str(SEED)):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    h.update(content)
    return CACHE_DIR / f"{h.hexdigest()}.json"


def _as_existing_path(source: str) -> Path | None:
    if len(source) < 260 and "\n" not in source:
        candidate = Path(source)
        if candidate.exists():
            return candidate
    return None

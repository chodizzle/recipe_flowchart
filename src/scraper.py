"""URL -> plain-text recipe, via the schema.org/Recipe JSON-LD block most recipe
sites embed. Pulls only the functional content (title, ingredients, instructions) --
not photos, headnotes, or other editorial content."""

from __future__ import annotations

import json
import re

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (recipe-flowchart research script)"}
_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def fetch_recipe_text(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=20)
    response.raise_for_status()

    recipe = _find_recipe_json_ld(response.text)
    if recipe is None:
        raise ValueError(f"No schema.org Recipe JSON-LD found at {url}")

    return _format_recipe(recipe)


def _find_recipe_json_ld(html: str) -> dict | None:
    for match in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(match.strip())
        except json.JSONDecodeError:
            continue
        for candidate in _iter_json_ld_nodes(data):
            if _is_recipe(candidate):
                return candidate
    return None


def _iter_json_ld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_json_ld_nodes(data["@graph"])


def _is_recipe(node: dict) -> bool:
    node_type = node.get("@type", "")
    types = node_type if isinstance(node_type, list) else [node_type]
    return "Recipe" in types


def _format_recipe(recipe: dict) -> str:
    title = recipe.get("name", "").strip()
    ingredients = recipe.get("recipeIngredient") or recipe.get("ingredients") or []
    instructions = _flatten_instructions(recipe.get("recipeInstructions", []))

    lines = [title, ""]
    lines.append("Ingredients:")
    lines.extend(f"- {i}" for i in ingredients)
    lines.append("")
    lines.append("Instructions:")
    lines.extend(f"{n}. {step}" for n, step in enumerate(instructions, start=1))
    return "\n".join(lines)


def _flatten_instructions(instructions) -> list[str]:
    if isinstance(instructions, str):
        return [s.strip() for s in instructions.split("\n") if s.strip()]

    steps: list[str] = []
    for item in instructions:
        if isinstance(item, str):
            steps.append(item.strip())
        elif isinstance(item, dict):
            if item.get("@type") == "HowToSection" and "itemListElement" in item:
                steps.extend(_flatten_instructions(item["itemListElement"]))
            else:
                text = item.get("text") or item.get("name") or ""
                if text:
                    steps.append(text.strip())
    return steps

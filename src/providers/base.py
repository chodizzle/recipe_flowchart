"""Shared interface and structured-output contract for recipe-extraction providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# This is a structuring task, not a creative one -- extraction should be as close to
# deterministic as each provider's API allows. temperature=0 is supported everywhere;
# `seed` is a best-effort determinism hint OpenAI and Gemini support and Anthropic doesn't.
TEMPERATURE = 0.0
SEED = 0

# Flat node shape (every field present, nullable where type-conditional) rather than a
# oneOf on `type` -- OpenAI's strict function-calling requires every property listed in
# `required`, and a flat shape behaves identically across both providers' implementations.
RECIPE_GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "The recipe's title"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Short unique node id, e.g. 'i1' or 'o1'"},
                    "type": {
                        "type": "string",
                        "enum": ["ingredient", "operation"],
                        "description": "'ingredient' is a raw input (always a layer-0 leaf); 'operation' is a technique applied to earlier nodes",
                    },
                    "name": {
                        "type": ["string", "null"],
                        "description": "Ingredient name, e.g. 'unsalted butter'. Null for operation nodes.",
                    },
                    "amount": {
                        "type": ["string", "null"],
                        "description": "Ingredient quantity as a single string, e.g. '1 cup (200 g)'. Null for operation nodes.",
                    },
                    "technique": {
                        "type": ["string", "null"],
                        "description": "Short imperative technique label for an operation, e.g. 'melt', 'mix', 'fold in', 'bake'. Null for ingredient nodes.",
                    },
                    "inputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of nodes (ingredients and/or upstream operations) this operation consumes. Always empty for ingredient nodes.",
                    },
                    "detail": {
                        "type": ["string", "null"],
                        "description": "Optional operation detail such as time/temperature, e.g. '350F (170C), 30-40 min'. Null if not applicable.",
                    },
                },
                "required": ["id", "type", "name", "amount", "technique", "inputs", "detail"],
            },
        },
    },
    "required": ["title", "nodes"],
}

EXTRACTION_INSTRUCTIONS = """You are extracting a recipe into a Gozinto-style dependency graph (an assembly chart: ingredients converge through operations into a finished dish).

First, set `title` to the dish's name -- its own stated title if given, otherwise a short accurate one you infer. This field is required and must never be left blank or omitted, no matter how long the node list below ends up being.

Then read the recipe -- text or a photo, possibly handwritten and mixing languages -- and emit a flat list of nodes of two kinds:

- ingredient nodes: one per line item (name + amount), always a layer-0 leaf with no inputs. Never merge multiple ingredients into one node.
- operation nodes: a short technique label (e.g. "melt", "mix", "fold in", "bake", not a full sentence) plus `inputs`, the ids of every node -- ingredients and/or earlier operations -- that this step consumes. `inputs` points BACKWARD at what feeds in, never forward. A non-ingredient setup action with nothing feeding into it yet (e.g. "preheat oven", "butter the pan") is still an operation node, just with an empty `inputs` list.

Order falls out of the graph itself (an operation's depth is 1 + the deepest of its inputs), so do not number steps or encode order any other way. Use `detail` for a stated time/temperature; leave it null otherwise.

Worked example -- input "Toast: 2 slices bread. Butter: 1 tbsp. Toast the bread. Spread the butter on the toast." produces title "Toast" and exactly these nodes:

  {"id": "i1", "type": "ingredient", "name": "bread", "amount": "2 slices", "technique": null, "inputs": [], "detail": null}
  {"id": "i2", "type": "ingredient", "name": "butter", "amount": "1 tbsp", "technique": null, "inputs": [], "detail": null}
  {"id": "o1", "type": "operation", "name": null, "amount": null, "technique": "toast", "inputs": ["i1"], "detail": null}
  {"id": "o2", "type": "operation", "name": null, "amount": null, "technique": "spread", "inputs": ["o1", "i2"], "detail": null}

Note how "spread" reaches back to both the toasted bread (o1) and the raw butter (i2) -- that convergence is exactly what `inputs` is for. Assign short sequential ids: i1, i2, ... for ingredients, o1, o2, ... for operations.

A temperature or heat-level statement on its own ("heat oil to 325F", "increase the heat to 375F") is never its own operation node -- fold it into the `detail` of whichever operation actually happens at that temperature. And regardless of temperature: reusing the same piece of equipment or resource (pan, oven, oil, wok) is a real dependency even when no ingredient is shared -- that operation's `inputs` must include whatever earlier operation last used the same resource, so operations end up chained in the order they actually happen, not just the order their own ingredients happen to be ready.

Second worked example -- input "Heat oil to 325F. Fry the pork, 2 min. Increase oil to 375F. Fry the pork again, 1 min. Add the peppers to the hot oil and fry, 1 min." (pork and peppers as ingredient nodes i1, i2) produces:

  {"id": "o1", "type": "operation", "name": null, "amount": null, "technique": "fry", "inputs": ["i1"], "detail": "325F (165C), 2 min"}
  {"id": "o2", "type": "operation", "name": null, "amount": null, "technique": "fry", "inputs": ["o1"], "detail": "375F (190C), 1 min"}
  {"id": "o3", "type": "operation", "name": null, "amount": null, "technique": "fry", "inputs": ["o2", "i2"], "detail": "1 min"}

Note "increase oil to 375F" is not its own node -- it's folded into o2's detail, and o2 still depends on o1 since it's the same oil, already in use. Note o3 (frying the peppers) depends on o2, not just on the peppers -- it reuses the same hot oil right after, so it must come after, even though nothing about the peppers themselves required that order."""


@dataclass
class ExtractionResult:
    provider: str
    model: str
    title: str
    nodes: list[dict]
    input_tokens: int
    output_tokens: int
    latency_s: float
    estimated_cost_usd: float


class GraphValidationError(ValueError):
    """A model's node list doesn't form a valid dependency graph."""


def validate_graph(nodes: list[dict]) -> None:
    """Every `inputs` id must resolve to a node that exists, and the graph must be acyclic."""
    ids = {n["id"] for n in nodes}
    if len(ids) != len(nodes):
        raise GraphValidationError("duplicate node ids in extraction result")

    for node in nodes:
        for dep in node.get("inputs") or []:
            if dep not in ids:
                raise GraphValidationError(f"node {node['id']!r} has unresolved input {dep!r}")

    # DFS cycle check over the inputs (dependency) edges.
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in nodes}
    by_node_id = {n["id"]: n for n in nodes}

    def visit(node_id: str, path: list[str]) -> None:
        color[node_id] = GRAY
        for dep in by_node_id[node_id].get("inputs") or []:
            if color[dep] == GRAY:
                cycle = " -> ".join(path + [dep])
                raise GraphValidationError(f"cycle detected: {cycle}")
            if color[dep] == WHITE:
                visit(dep, path + [dep])
        color[node_id] = BLACK

    for node in nodes:
        if color[node["id"]] == WHITE:
            visit(node["id"], [node["id"]])


class Provider(ABC):
    name: str

    @abstractmethod
    def extract_from_text(self, text: str, model: str) -> ExtractionResult: ...

    @abstractmethod
    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult: ...

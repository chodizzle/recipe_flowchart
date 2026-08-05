"""LLM-as-judge: ask a model to score an extraction run against the exact same taxonomy
John used by hand (see taxonomy.py), so its output is directly comparable to a human
score file in eval/scores/.

The judge sees exactly what the extractor saw (the recipe text or photo) plus the
extractor's raw node graph as JSON -- never the rendered HTML table, since layout_bug is
a property of gozinto_render.py, not the extraction, and the judge has no way to assess
it without seeing the render (see taxonomy.JUDGE_TAG_KEYS, which excludes it).

Calls are cached the same way src/recipe_parser.py caches extractions: content-addressed
on everything that could change the output, so a prompt/schema edit can't silently serve
a stale judgment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import anthropic  # noqa: E402

from taxonomy import JUDGE_TAG_KEYS, MISSING_CHECKLIST, MISSING_KEYS, TAXONOMY  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "judge"

TEMPERATURE = 0.0

# USD per million tokens: (input, output).
PRICING_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}

_TAG_LINES = "\n".join(f'- "{t["key"]}": {t["label"]} -- {t["hint"]}' for t in TAXONOMY if t["key"] in JUDGE_TAG_KEYS)
_MISSING_LINES = "\n".join(f'- "{m["key"]}": {m["label"]}' for m in MISSING_CHECKLIST)

JUDGE_INSTRUCTIONS = f"""You are a professional chef reviewing a machine-extracted Gozinto
dependency graph against the original recipe (text or photo). The graph has two node
types: "ingredient" (a raw input, leaf-level) and "operation" (a technique applied to
earlier nodes, referencing them via `inputs`).

Judge the graph the way an expert cook would -- hold it to a standard of "does this
correctly capture how the dish is actually made," not pedantic nitpicking.

For every node with a real problem, flag it with one or more of these tags:
{_TAG_LINES}

Multiple tags can apply to the same node (e.g. both a wrong technique name AND a wrong
set of ingredients grouped into it) -- flag every tag that genuinely applies, not just one.

Separately, these whole-run checklist items are for something that never made it into the
graph at all (so there's no node to attach a per-node tag to):
{_MISSING_LINES}

Only flag genuine problems. A node with nothing wrong should not appear in your output at
all -- do not flag it just to have something to say."""

_SCHEMA_TEMPLATE = {
    "type": "object",
    "properties": {
        "flagged_nodes": {
            "type": "array",
            "description": "Only nodes with a genuine problem. Omit anything correct.",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "Must match a node id from the provided graph."},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string", "enum": JUDGE_TAG_KEYS},
                        "minItems": 1,
                    },
                },
                "required": ["node_id", "tags"],
            },
        },
        **{key: {"type": "boolean"} for key in MISSING_KEYS},
    },
    "required": ["flagged_nodes", *MISSING_KEYS],
}

_TOOL_NAME = "record_judgment"


@dataclass
class JudgeResult:
    model: str
    cell_flags: dict[str, list[str]]
    missing_flags: dict[str, bool]
    input_tokens: int
    output_tokens: int
    latency_s: float
    estimated_cost_usd: float


def judge_run(
    recipe_path: Path,
    title: str,
    nodes: list[dict],
    model: str = "claude-sonnet-5",
    use_cache: bool = True,
) -> JudgeResult:
    node_ids = [n["id"] for n in nodes]
    schema = json.loads(json.dumps(_SCHEMA_TEMPLATE))  # cheap deep copy
    schema["properties"]["flagged_nodes"]["items"]["properties"]["node_id"]["enum"] = node_ids

    recipe_bytes = recipe_path.read_bytes()
    cache_path = _cache_path(model, recipe_bytes, nodes, schema)
    if use_cache and cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return JudgeResult(**data)

    result = _call_anthropic(model, recipe_path, recipe_bytes, title, nodes, schema)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def _call_anthropic(
    model: str, recipe_path: Path, recipe_bytes: bytes, title: str, nodes: list[dict], schema: dict
) -> JudgeResult:
    client = anthropic.Anthropic()
    graph_json = json.dumps({"title": title, "nodes": nodes}, indent=2)

    is_image = recipe_path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    if is_image:
        media_type = "image/jpeg" if recipe_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.standard_b64encode(recipe_bytes).decode("utf-8")
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": f"Extracted graph (JSON) to judge against this photo:\n\n{graph_json}"},
        ]
    else:
        recipe_text = recipe_bytes.decode("utf-8")
        content = f"Recipe:\n\n{recipe_text}\n\nExtracted graph (JSON) to judge:\n\n{graph_json}"

    tool = {"name": _TOOL_NAME, "description": "Record the judgment.", "input_schema": schema}
    kwargs = dict(
        model=model,
        max_tokens=4096,
        system=JUDGE_INSTRUCTIONS,
        tools=[tool],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": content}],
    )
    start = time.perf_counter()
    try:
        response = client.messages.create(temperature=TEMPERATURE, **kwargs)
    except anthropic.BadRequestError as e:
        if "temperature" not in str(e):
            raise
        response = client.messages.create(**kwargs)
    latency = time.perf_counter() - start

    tool_use = next(b for b in response.content if b.type == "tool_use")
    data = tool_use.input
    cell_flags = {item["node_id"]: item["tags"] for item in data.get("flagged_nodes", [])}
    missing_flags = {key: bool(data.get(key, False)) for key in MISSING_KEYS}

    in_rate, out_rate = PRICING_PER_MTOK.get(model, (0.0, 0.0))
    cost = (response.usage.input_tokens / 1e6) * in_rate + (response.usage.output_tokens / 1e6) * out_rate

    return JudgeResult(
        model=model,
        cell_flags=cell_flags,
        missing_flags=missing_flags,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_s=latency,
        estimated_cost_usd=cost,
    )


def _cache_path(model: str, recipe_bytes: bytes, nodes: list[dict], schema: dict) -> Path:
    h = hashlib.sha256()
    for part in (model, JUDGE_INSTRUCTIONS, json.dumps(schema, sort_keys=True), json.dumps(nodes, sort_keys=True), str(TEMPERATURE)):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    h.update(recipe_bytes)
    return CACHE_DIR / f"{h.hexdigest()}.json"

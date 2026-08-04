"""Local-only expert-eval scoring tool.

Shows each of the 18 (recipe x model) runs side by side -- source recipe on the left,
rendered Gozinto table on the right -- and lets a human expert click a cell to tag *why*
it's wrong from a fixed taxonomy (no free text). Every click persists immediately to
`eval/scores/<run_id>.json`, so nothing is lost across sessions.

Run with: `.venv/Scripts/python.exe eval/app.py` then open http://127.0.0.1:5050
Never hits a provider API: it only reads results already sitting in the extraction
cache (`is_cached`), so opening this tool costs nothing.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_file  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

from build_site import RECIPES, RUNS  # noqa: E402
from gozinto_render import to_table_html  # noqa: E402
from recipe_parser import is_cached, parse_recipe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORES_DIR = Path(__file__).resolve().parent / "scores"
SCORES_DIR.mkdir(exist_ok=True)

TAXONOMY = [
    {"key": "decomposition", "label": "Decomposition", "hint": "wrong/missing amount for this step", "color": "#3b82f6"},
    {"key": "grouping", "label": "Grouping", "hint": "wrong ingredients combined here", "color": "#8b5cf6"},
    {"key": "method", "label": "Method", "hint": "wrong technique verb", "color": "#f59e0b"},
    {"key": "prep", "label": "Prep/modifier", "hint": "missing detail like 'cubed'", "color": "#14b8a6"},
    {"key": "timing", "label": "Timing", "hint": "wrong or missing time/temp", "color": "#ec4899"},
    {"key": "order", "label": "Order", "hint": "wrong sequence", "color": "#ef4444"},
    {"key": "extraneous", "label": "Extraneous", "hint": "this node shouldn't exist at all", "color": "#84cc16"},
    # Fault-attribution tags -- combine with any tag above to say "flagged, but don't
    # count it against the model." Two causes kept separate since they need different fixes:
    # layout_bug means our own render code is wrong, ambiguous_source means the recipe is.
    {"key": "layout_bug", "label": "Layout bug", "hint": "render placed it wrong -- not the model's fault", "color": "#6b7280"},
    {"key": "ambiguous_source", "label": "Ambiguous source", "hint": "recipe itself unclear here -- don't fault the model", "color": "#94a3b8"},
]

MISSING_CHECKLIST = [
    {"key": "missing_ingredient", "label": "Missing ingredient"},
    {"key": "missing_setup", "label": "Missing setup/prep step (e.g. preheat oven)"},
    {"key": "missing_operation", "label": "Missing operation step"},
]


def _build_runs() -> list[dict]:
    runs = []
    for recipe in RECIPES:
        if not recipe["input"].exists():
            continue
        for provider, model, label in RUNS:
            run_id = f"{recipe['id']}__{provider}-{model}"
            if not is_cached(recipe["input"], provider, model):
                print(f"skipping {run_id}: not in cache -- run build_site.py first")
                continue
            result = parse_recipe(recipe["input"], provider, model, use_cache=True)
            is_image = recipe["input"].suffix.lower() in {".jpg", ".jpeg", ".png"}
            runs.append(
                {
                    "run_id": run_id,
                    "recipe_id": recipe["id"],
                    "recipe_label": recipe["label"],
                    "recipe_source": recipe["source"],
                    "is_image": is_image,
                    "recipe_text": None if is_image else recipe["input"].read_text(encoding="utf-8"),
                    "model_label": label,
                    "provider": provider,
                    "model": model,
                    "title": result.title,
                    "table_html": to_table_html(result.nodes),
                    "nodes": result.nodes,
                }
            )
    return runs


ALL_RUNS = _build_runs()
RUN_INDEX = {r["run_id"]: i for i, r in enumerate(ALL_RUNS)}


def _score_path(run_id: str) -> Path:
    return SCORES_DIR / f"{run_id}.json"


def _load_score(run_id: str) -> dict:
    path = _score_path(run_id)
    if not path.exists():
        return {"run_id": run_id, "cell_flags": {}, "missing_flags": {}, "reviewed": False, "updated_at": None}
    score = json.loads(path.read_text(encoding="utf-8"))
    # Pre-multi-tag files stored one tag per cell as a bare string; normalize to a list
    # so old scoring sessions don't lose data when this file is next re-saved.
    score["cell_flags"] = {
        node_id: ([tag] if isinstance(tag, str) else tag) for node_id, tag in score["cell_flags"].items()
    }
    return score


def _save_score(run_id: str, score: dict) -> None:
    score["updated_at"] = datetime.now(timezone.utc).isoformat()
    _score_path(run_id).write_text(json.dumps(score, indent=2), encoding="utf-8")


env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent / "templates")),
    autoescape=select_autoescape(["html"]),
)

app = Flask(__name__)


@app.route("/")
def index():
    return _render_run(0)


@app.route("/run/<int:idx>")
def run_page(idx: int):
    return _render_run(idx)


def _render_run(idx: int):
    if not ALL_RUNS:
        return "No cached runs found. Run `python src/build_site.py` first.", 500
    idx = max(0, min(idx, len(ALL_RUNS) - 1))
    run = ALL_RUNS[idx]
    score = _load_score(run["run_id"])
    reviewed_map = {r["run_id"]: _load_score(r["run_id"])["reviewed"] for r in ALL_RUNS}
    reviewed_count = sum(1 for v in reviewed_map.values() if v)
    template = env.get_template("index.html")
    return template.render(
        run=run,
        idx=idx,
        total=len(ALL_RUNS),
        all_runs=ALL_RUNS,
        score=score,
        taxonomy=TAXONOMY,
        missing_checklist=MISSING_CHECKLIST,
        reviewed_count=reviewed_count,
        reviewed_map=reviewed_map,
    )


@app.route("/media/<recipe_id>")
def media(recipe_id: str):
    recipe = next((r for r in RECIPES if r["id"] == recipe_id), None)
    if recipe is None or not recipe["input"].exists():
        return "not found", 404
    return send_file(recipe["input"])


@app.route("/api/flag", methods=["POST"])
def api_flag():
    """Toggle a single tag in a node's tag list (a cell can carry more than one flag,
    e.g. both a wrong technique AND a wrong grouping on the same operation)."""
    body = request.get_json()
    run_id, node_id, tag = body["run_id"], body["node_id"], body["tag"]
    score = _load_score(run_id)
    tags = score["cell_flags"].get(node_id, [])
    tags = [t for t in tags if t != tag] if tag in tags else tags + [tag]
    if tags:
        score["cell_flags"][node_id] = tags
        score["reviewed"] = True
    else:
        score["cell_flags"].pop(node_id, None)
    _save_score(run_id, score)
    return jsonify(score)


@app.route("/api/missing", methods=["POST"])
def api_missing():
    body = request.get_json()
    run_id, key, checked = body["run_id"], body["key"], body["checked"]
    score = _load_score(run_id)
    score["missing_flags"][key] = checked
    if checked:
        score["reviewed"] = True
    _save_score(run_id, score)
    return jsonify(score)


@app.route("/api/review", methods=["POST"])
def api_review():
    body = request.get_json()
    run_id = body["run_id"]
    score = _load_score(run_id)
    score["reviewed"] = bool(body.get("reviewed", True))
    _save_score(run_id, score)
    return jsonify(score)


if __name__ == "__main__":
    print(f"{len(ALL_RUNS)} runs loaded from cache")
    app.run(port=5050, debug=True)

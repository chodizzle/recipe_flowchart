"""Runs the recipe -> flowchart pipeline across recipes x models and renders docs/index.html.

This is the whole "build": no live backend, no API key touches the browser. Run it
locally (`python src/build_site.py`) whenever the example recipes or provider code
change, and commit the regenerated docs/index.html.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from gozinto_render import to_table_html  # noqa: E402
from providers.base import ExtractionResult  # noqa: E402
from recipe_parser import is_cached, parse_recipe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = ROOT / "data" / "recipes"
DOCS_DIR = ROOT / "docs"
MEDIA_DIR = DOCS_DIR / "media"
SCREENSHOTS_DIR = ROOT / "screenshots"
SCORES_DIR = ROOT / "eval" / "scores"

# Full worked example (rendered Gozinto + per-model stats table); every other recipe gets
# summarized, not fully rendered -- 10 full tables was too much to scroll through. Picked
# for size (10 ingredients, vs. 22+ for some others) without giving up structure (11
# operations, 5 merges -- more ops than ingredients, real convergence to look at).
SHOWCASE_RECIPE_ID = "complex"

# The "no single correct answer" finding (see README) -- models that all scored zero
# human-flagged issues on this recipe, with genuinely different graphs. The two shown are
# the biggest structural spread of the three that qualified (7 ops vs. 10 ops), not all
# three, since the point lands better with the clearest contrast than with every example.
# Curated by hand, not auto-selected, since the point is a specific, verified example.
GRANULARITY_RECIPE_ID = "roast_potatoes"
GRANULARITY_MODELS = [
    ("openai", "gpt-4o", "GPT-4o"),
    ("anthropic", "claude-sonnet-5", "Claude Sonnet 5"),
]

RECIPES = [
    {
        "id": "cooked",
        "label": "Cooked",
        "source": "Serious Eats",
        "source_url": "",
        "input": RECIPES_DIR / "01_cooked.txt",
    },
    {
        "id": "baked",
        "label": "Baked",
        "source": "NYT Cooking",
        "source_url": "",
        "input": RECIPES_DIR / "02_baked.txt",
    },
    {
        "id": "complex",
        "label": "Handwritten",
        "source": "My own kitchen notes (bilingual shorthand, hand-drawn dependency brackets)",
        "source_url": "",
        "input": RECIPES_DIR / "03_choux_au_craquelin.jpg",
    },
    {
        "id": "roast_potatoes",
        "label": "Web Scrape",
        "source": "Serious Eats (J. Kenji López-Alt)",
        "source_url": "https://www.seriouseats.com/the-best-roast-potatoes-ever-recipe",
        "input": RECIPES_DIR / "04_roast_potatoes.txt",
    },
    {
        "id": "pancakes",
        "label": "Pancakes",
        "source": "Serious Eats (J. Kenji López-Alt)",
        "source_url": "",
        "input": RECIPES_DIR / "05_pancakes.txt",
    },
    {
        "id": "eggnog",
        "label": "Eggnog",
        "source": "Alton Brown",
        "source_url": "",
        "input": RECIPES_DIR / "06_eggnog.txt",
    },
    {
        "id": "mac_and_cheese",
        "label": "Mac & Cheese",
        "source": "Food Network (Alton Brown)",
        "source_url": "https://www.foodnetwork.com/recipes/alton-brown/stovetop-mac-n-cheese-recipe-1939465",
        "input": RECIPES_DIR / "07_mac_and_cheese.txt",
    },
    {
        "id": "potstickers",
        "label": "Potstickers",
        "source": "Damn Delicious",
        "source_url": "",
        "input": RECIPES_DIR / "08_potstickers.txt",
    },
    {
        "id": "shredded_beef",
        "label": "Shredded Beef Tacos",
        "source": "RecipeTin Eats (Nagi)",
        "source_url": "",
        "input": RECIPES_DIR / "09_mexican_shredded_beef.txt",
    },
    {
        "id": "tikka_masala",
        "label": "Tikka Masala",
        "source": "Savory Tooth",
        "source_url": "",
        "input": RECIPES_DIR / "10_chicken_tikka_masala.txt",
    },
]

# (provider, model, display label). The last entry drives the displayed diagram.
RUNS = [
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5"),
    ("anthropic", "claude-sonnet-5", "Claude Sonnet 5"),
    ("openai", "gpt-4o-mini", "GPT-4o mini"),
    ("openai", "gpt-4o", "GPT-4o"),
    ("google", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
    ("google", "gemini-3.5-flash", "Gemini 3.5 Flash"),
]
PRIMARY_LABEL = "Claude Sonnet 5"


def run_pipeline(use_cache: bool = True) -> list[tuple[dict, list[tuple[str, ExtractionResult]]]]:
    all_results = []
    for recipe in RECIPES:
        if not recipe["input"].exists():
            print(f"skipping {recipe['id']}: {recipe['input']} not found")
            continue
        recipe_results = []
        for provider, model, label in RUNS:
            cache_hit = use_cache and is_cached(recipe["input"], provider, model)
            result = parse_recipe(recipe["input"], provider, model, use_cache=use_cache)
            recipe_results.append((label, result))
            n_ingredients, n_operations, n_merges = _node_counts(result.nodes)
            print(
                f"{recipe['id']:>8} | {label:<22} | "
                f"{result.input_tokens:>5}in {result.output_tokens:>4}out | "
                f"${result.estimated_cost_usd:.4f} | {result.latency_s:5.1f}s | "
                f"{n_ingredients:>2} ingredients, {n_operations:>2} ops ({n_merges} merges)"
                f"{'  [cached]' if cache_hit else ''}"
            )
        all_results.append((recipe, recipe_results))
    return all_results


def render_html(all_results: list[tuple[dict, list[tuple[str, ExtractionResult]]]]) -> str:
    by_id = {recipe["id"]: (recipe, results) for recipe, results in all_results}

    showcase_recipe, showcase_results = by_id[SHOWCASE_RECIPE_ID]
    showcase_card = _render_recipe_card(showcase_recipe, showcase_results)

    recipe_list = _render_recipe_list(all_results)
    model_rollup = _render_model_rollup(all_results)
    granularity_section = _render_granularity_comparison(by_id)

    return _PAGE_TEMPLATE.format(
        showcase_card=showcase_card,
        recipe_list=recipe_list,
        model_rollup=model_rollup,
        granularity_section=granularity_section,
    )


def _node_counts(nodes: list[dict]) -> tuple[int, int, int]:
    n_ingredients = sum(1 for n in nodes if n["type"] == "ingredient")
    operations = [n for n in nodes if n["type"] == "operation"]
    n_merges = sum(1 for op in operations if len(op.get("inputs") or []) >= 2)
    return n_ingredients, len(operations), n_merges


def _render_recipe_card(recipe: dict, results: list[tuple[str, ExtractionResult]]) -> str:
    primary = next((r for label, r in results if label == PRIMARY_LABEL), results[-1][1])
    table = to_table_html(primary.nodes)
    # A model occasionally drops the required `title` field on large outputs (see README);
    # fall back to any run that did get it rather than leaving the heading blank.
    title = primary.title or next((r.title for _, r in results if r.title), "")
    source_line = (
        f'<a href="{html.escape(recipe["source_url"])}">{html.escape(recipe["source"])}</a>'
        if recipe["source_url"]
        else html.escape(recipe["source"])
    )
    rows = "\n".join(_render_table_row(label, r) for label, r in results)
    return f"""
  <section class="card">
    <h2>{html.escape(recipe["label"])}: {html.escape(title)}</h2>
    <p class="tagline">Source: {source_line}</p>
    {table}
    <table class="stats">
      <thead><tr><th>Model</th><th>Input tok</th><th>Output tok</th><th>Cost</th><th>Latency</th><th>Ingredients</th><th>Operations</th><th>Merges</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </section>"""


def _render_table_row(label: str, r: ExtractionResult) -> str:
    n_ingredients, n_operations, n_merges = _node_counts(r.nodes)
    highlight = ' class="primary"' if label == PRIMARY_LABEL else ""
    return (
        f"        <tr{highlight}><td>{html.escape(label)}</td><td>{r.input_tokens}</td>"
        f"<td>{r.output_tokens}</td><td>${r.estimated_cost_usd:.4f}</td>"
        f"<td>{r.latency_s:.1f}s</td><td>{n_ingredients}</td><td>{n_operations}</td><td>{n_merges}</td></tr>"
    )


def _render_recipe_list(all_results: list[tuple[dict, list[tuple[str, ExtractionResult]]]]) -> str:
    items = []
    for recipe, _ in all_results:
        source_line = (
            f'<a href="{html.escape(recipe["source_url"])}">{html.escape(recipe["source"])}</a>'
            if recipe["source_url"]
            else html.escape(recipe["source"])
        )
        items.append(f'      <li><strong>{html.escape(recipe["label"])}</strong> &mdash; {source_line}</li>')
    return "\n".join(items)


def _eval_issue_counts() -> dict[str, int]:
    """Total human-flagged issues per provider-model key, read straight from the eval
    tool's own score files -- real numbers, not re-derived or approximated."""
    counts: dict[str, int] = {}
    if not SCORES_DIR.exists():
        return counts
    for f in SCORES_DIR.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        _, model_key = data["run_id"].split("__", 1)
        n = sum(len(v) for v in data["cell_flags"].values())
        n += sum(1 for v in data["missing_flags"].values() if v)
        counts[model_key] = counts.get(model_key, 0) + n
    return counts


def _render_model_rollup(all_results: list[tuple[dict, list[tuple[str, ExtractionResult]]]]) -> str:
    issue_counts = _eval_issue_counts()
    totals: dict[str, dict] = {}
    for provider, model, label in RUNS:
        totals[label] = {"cost": 0.0, "latency": 0.0, "n": 0, "issues": issue_counts.get(f"{provider}-{model}", 0)}
    for _, results in all_results:
        for label, r in results:
            t = totals[label]
            t["cost"] += r.estimated_cost_usd
            t["latency"] += r.latency_s
            t["n"] += 1

    rows = []
    for label, t in sorted(totals.items(), key=lambda kv: kv[1]["issues"]):
        avg_latency = t["latency"] / t["n"] if t["n"] else 0.0
        highlight = ' class="primary"' if label == PRIMARY_LABEL else ""
        rows.append(
            f"        <tr{highlight}><td>{html.escape(label)}</td><td>${t['cost']:.4f}</td>"
            f"<td>{avg_latency:.1f}s</td><td>{t['issues']}</td></tr>"
        )
    return "\n".join(rows)


def _render_granularity_comparison(by_id: dict[str, tuple[dict, list]]) -> str:
    recipe, _ = by_id[GRANULARITY_RECIPE_ID]
    columns = []
    for provider, model, label in GRANULARITY_MODELS:
        r = parse_recipe(recipe["input"], provider, model, use_cache=True)
        n_ingredients, n_operations, n_merges = _node_counts(r.nodes)
        columns.append(f"""
      <div class="granularity-col">
        <h3>{html.escape(label)}</h3>
        <p class="tagline">{n_operations} operations, {n_merges} merges &mdash; scored zero issues</p>
        {to_table_html(r.nodes)}
      </div>""")
    return "\n".join(columns)


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recipe Flowchart</title>
<style>
  :root {{
    --bg: #ffffff;
    --fg: #1a1a1a;
    --muted: #5a5a5a;
    --card: #f6f6f7;
    --border: #e2e2e4;
    --accent: #b3261e;
    --accent2: #1a7f37;
    --code-bg: #f0f0f1;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #12141a;
      --fg: #e8e8ea;
      --muted: #a2a3aa;
      --card: #1b1e26;
      --border: #2b2e38;
      --accent: #ff7a70;
      --accent2: #5fd38a;
      --code-bg: #1d2029;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
  }}
  main {{ max-width: 860px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }}
  h1 {{ font-size: 1.9rem; margin-bottom: 0.3rem; }}
  .tagline {{ color: var(--muted); font-size: 1.0rem; margin-top: 0; }}
  h2 {{ margin-top: 0; font-size: 1.25rem; }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin: 1.6rem 0;
    overflow-x: auto;
  }}
  table.gozinto {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; font-size: 0.9rem; }}
  table.gozinto td {{ border: 1px solid var(--border); padding: 0.55rem 0.75rem; vertical-align: middle; }}
  table.gozinto td.ingredient {{ background: var(--bg); }}
  table.gozinto td.ingredient .name {{ display: block; font-weight: 600; }}
  table.gozinto td.ingredient .amount {{ display: block; color: var(--muted); font-size: 0.85em; }}
  table.gozinto td.op {{ background: var(--card); border-left: 4px solid var(--accent2); border-radius: 0 8px 8px 0; text-align: center; }}
  table.gozinto td.op .technique {{ display: block; font-weight: 600; text-transform: capitalize; }}
  table.gozinto td.op .detail {{ display: block; color: var(--muted); font-size: 0.8em; margin-top: 0.15rem; }}
  table.gozinto td.empty {{ border-color: transparent; background: transparent; }}
  table.gozinto td.setup {{ background: var(--code-bg); font-weight: 600; text-align: left; border-left: 4px solid var(--accent); }}
  table.stats {{ border-collapse: collapse; width: 100%; margin-top: 1.4rem; font-size: 0.88rem; }}
  table.stats th, table.stats td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }}
  table.stats th {{ color: var(--muted); font-weight: 600; }}
  table.stats tr.primary td {{ font-weight: 600; }}
  a {{ color: var(--accent2); }}
  code {{ background: var(--code-bg); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9em; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.85rem; }}

  section.section {{ margin: 2.6rem 0; }}
  section.section h2 {{ font-size: 1.4rem; }}
  .eval-media {{ display: flex; gap: 1.2rem; flex-wrap: wrap; align-items: flex-start; margin-top: 1rem; }}
  .eval-media video {{ max-width: 100%; width: 480px; border-radius: 8px; border: 1px solid var(--border); }}
  .eval-media .screenshots {{ display: flex; gap: 0.8rem; flex-wrap: wrap; }}
  .eval-media img {{ max-width: 220px; width: 100%; border-radius: 8px; border: 1px solid var(--border); }}
  .recipe-list {{ columns: 2; column-gap: 2rem; padding-left: 1.1rem; margin: 1rem 0; }}
  .recipe-list li {{ break-inside: avoid; margin-bottom: 0.3rem; }}
  @media (max-width: 640px) {{ .recipe-list {{ columns: 1; }} }}
  .granularity-wrap {{ display: flex; flex-direction: column; gap: 1.4rem; margin-top: 1rem; }}
  .granularity-col {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.1rem 1.3rem; overflow-x: auto; }}
  .granularity-col h3 {{ margin: 0 0 0.2rem; font-size: 1.1rem; }}
</style>
</head>
<body>
<main>
  <h1>Recipe Flowchart</h1>
  <p class="tagline">LLMs can structure your data. Knowing whether they got it right is the actual work.</p>
  <p>Turning a recipe into a Gozinto chart (an assembly diagram: ingredients converge through operations into a finished dish) is easy for an LLM to do. What's actually hard is that there's no ground-truth dataset for "is this correct" &mdash; only a domain expert's judgment. This project is a worked example of building that eval loop for real: a taxonomy-based human scoring tool, a bug found and fixed and re-validated against the same rubric that found it, an automated judge tried and honestly closed, and a finding that this kind of task doesn't even have one correct answer. The model comparison below is real, but it's supporting material, not the point.</p>

  <section class="section">
    <h2>The eval tool</h2>
    <p>Every one of the 60 runs below was scored by hand against a fixed taxonomy (click a cell, tag why it's wrong, no free text) in a local tool built for exactly this. It isn't part of this static site &mdash; it writes real annotation data to disk, which a GitHub Pages site can't do &mdash; so here's what it looks like in use instead.</p>
    <div class="eval-media">
      <video src="media/eval_demo.mp4" controls preload="metadata"></video>
      <div class="screenshots">
        <img src="media/eval_1.png" alt="Eval tool: recipe source next to the rendered Gozinto chart, click-to-tag interface">
        <img src="media/eval_2.png" alt="Eval tool: tag popover open on a flagged cell, showing the taxonomy and the resolved raw inputs">
      </div>
    </div>
  </section>

  <section class="section">
    <h2>Worked example</h2>
    <p>One recipe shown in full &mdash; the rendered graph plus how all 6 models did on it. Picked for size, not drama: compact enough to read without a lot of scrolling, but still dense with the kind of convergence (multiple ingredients folding into one operation) that makes a Gozinto chart worth looking at. It's also the most visually distinctive input in the set &mdash; a photo of my own handwritten, bilingual kitchen notes, with hand-drawn brackets already marking which sub-steps run in parallel.</p>
{showcase_card}
  </section>

  <section class="section">
    <h2>All 10 recipes</h2>
    <p>Chosen to stress-test specific things, not just to pad the count &mdash; genuine parallel prep, raw unedited web-scrape noise, several variations on ingredients that split across steps, and one recipe added specifically to check whether the bug fix above generalized.</p>
    <ul class="recipe-list">
{recipe_list}
    </ul>
    <table class="stats">
      <thead><tr><th>Model</th><th>Total cost (10 recipes)</th><th>Avg latency</th><th>Human-flagged issues (60 runs)</th></tr></thead>
      <tbody>
{model_rollup}
      </tbody>
    </table>
  </section>

  <section class="section">
    <h2>Same recipe, two different (and equally correct) structures</h2>
    <p>Both of these models scored <strong>zero</strong> human-flagged issues on the same recipe &mdash; and produced genuinely different graphs, the biggest structural gap of any pair that both scored clean. GPT-4o folds "boil water" into the potato-boiling step and does the whole roast as one operation. Claude Sonnet 5 splits both out: its own "boil water" step, and the roast broken into its two real phases (undisturbed, then flip-and-continue). Neither is more correct than the other &mdash; they're different, equally valid choices about how finely to decompose a continuous process, which is the real reason this project didn't try to grade against one canonical answer.</p>
    <div class="granularity-wrap">
{granularity_section}
    </div>
  </section>

  <footer>Full pipeline, eval tool, and write-up: <a href="https://github.com/chodizzle/recipe_flowchart">github.com/chodizzle/recipe_flowchart</a>.</footer>
</main>
</body>
</html>
"""


def main(use_cache: bool = True) -> None:
    """Callable entry point -- takes `use_cache` directly so it's safe to call from the
    notebook or any other caller without going through argv (Jupyter's own kernel args
    would otherwise confuse an argparse call inside here)."""
    all_results = run_pipeline(use_cache=use_cache)
    if not all_results:
        print("No recipes found -- nothing to render.")
        return
    DOCS_DIR.mkdir(exist_ok=True)
    _copy_media()
    (DOCS_DIR / "index.html").write_text(render_html(all_results), encoding="utf-8")
    print(f"wrote {DOCS_DIR / 'index.html'}")


def _copy_media() -> None:
    """GitHub Pages serves only from docs/, so the eval-tool demo assets have to live
    there too, not just in the repo-root screenshots/ folder they're recorded into."""
    MEDIA_DIR.mkdir(exist_ok=True)
    for name in ("eval_demo.mp4", "eval_1.png", "eval_2.png"):
        src = SCREENSHOTS_DIR / name
        if src.exists():
            shutil.copy(src, MEDIA_DIR / name)
        else:
            print(f"warning: {src} not found, site will have a broken media reference")


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fresh", action="store_true", help="bypass the extraction cache and re-hit every API"
    )
    args = parser.parse_args()
    main(use_cache=not args.fresh)


if __name__ == "__main__":
    _cli()

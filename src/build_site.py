"""Runs the recipe -> flowchart pipeline across recipes x models and renders docs/index.html.

This is the whole "build": no live backend, no API key touches the browser. Run it
locally (`python src/build_site.py`) whenever the example recipes or provider code
change, and commit the regenerated docs/index.html.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from flowchart import to_mermaid  # noqa: E402
from providers.base import ExtractionResult  # noqa: E402
from recipe_parser import parse_recipe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = ROOT / "data" / "recipes"
DOCS_DIR = ROOT / "docs"

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
]

# (provider, model, display label). The last entry drives the displayed diagram.
RUNS = [
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5"),
    ("anthropic", "claude-sonnet-5", "Claude Sonnet 5"),
    ("openai", "gpt-4o-mini", "GPT-4o mini"),
    ("openai", "gpt-4o", "GPT-4o"),
]
PRIMARY_LABEL = "Claude Sonnet 5"


def run_pipeline() -> list[tuple[dict, list[tuple[str, ExtractionResult]]]]:
    all_results = []
    for recipe in RECIPES:
        if not recipe["input"].exists():
            print(f"skipping {recipe['id']}: {recipe['input']} not found")
            continue
        recipe_results = []
        for provider, model, label in RUNS:
            result = parse_recipe(recipe["input"], provider, model)
            recipe_results.append((label, result))
            n_independent = sum(1 for s in result.steps if not s.get("depends_on"))
            print(
                f"{recipe['id']:>8} | {label:<16} | "
                f"{result.input_tokens:>5}in {result.output_tokens:>4}out | "
                f"${result.estimated_cost_usd:.4f} | {result.latency_s:5.1f}s | "
                f"{len(result.steps):>2} steps ({n_independent} independent)"
            )
        all_results.append((recipe, recipe_results))
    return all_results


def render_html(all_results: list[tuple[dict, list[tuple[str, ExtractionResult]]]]) -> str:
    cards = "\n".join(_render_recipe_card(recipe, results) for recipe, results in all_results)
    return _PAGE_TEMPLATE.format(cards=cards)


def _render_recipe_card(recipe: dict, results: list[tuple[str, ExtractionResult]]) -> str:
    primary = next((r for label, r in results if label == PRIMARY_LABEL), results[-1][1])
    mermaid = to_mermaid(primary.steps)
    source_line = (
        f'<a href="{html.escape(recipe["source_url"])}">{html.escape(recipe["source"])}</a>'
        if recipe["source_url"]
        else html.escape(recipe["source"])
    )
    rows = "\n".join(_render_table_row(label, r) for label, r in results)
    return f"""
  <section class="card">
    <h2>{html.escape(recipe["label"])}: {html.escape(primary.title)}</h2>
    <p class="tagline">Source: {source_line}</p>
    <pre class="mermaid">
{html.escape(mermaid)}
    </pre>
    <table>
      <thead><tr><th>Model</th><th>Input tok</th><th>Output tok</th><th>Cost</th><th>Latency</th><th>Steps</th><th>Independent</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </section>"""


def _render_table_row(label: str, r: ExtractionResult) -> str:
    n_independent = sum(1 for s in r.steps if not s.get("depends_on"))
    highlight = ' class="primary"' if label == PRIMARY_LABEL else ""
    return (
        f"        <tr{highlight}><td>{html.escape(label)}</td><td>{r.input_tokens}</td>"
        f"<td>{r.output_tokens}</td><td>${r.estimated_cost_usd:.4f}</td>"
        f"<td>{r.latency_s:.1f}s</td><td>{len(r.steps)}</td><td>{n_independent}</td></tr>"
    )


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
  pre.mermaid {{ background: var(--bg); border-radius: 8px; padding: 0.5rem; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: 0.88rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; }}
  tr.primary td {{ font-weight: 600; }}
  a {{ color: var(--accent2); }}
  code {{ background: var(--code-bg); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9em; }}
  footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.85rem; }}
</style>
</head>
<body>
<main>
  <h1>Recipe Flowchart</h1>
  <p class="tagline">Turning recipes into dependency graphs -- and testing how cheap a model can be while still getting the graph right.</p>
  <p>Structuring unstructured text used to mean regex and endless if-chains. LLMs are now good enough, and cheap enough, to do it directly: each recipe below was run through the same forced-JSON extraction across four models, from a $1/MTok model up to full-price flagships, so the comparison table shows what you actually pay for accuracy versus what you don't.</p>

{cards}

  <footer>Full pipeline, provider code, and example recipes: <a href="https://github.com/chodizzle/recipe_flowchart">github.com/chodizzle/recipe_flowchart</a>.</footer>
</main>
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({{ startOnLoad: true, theme: dark ? "dark" : "neutral" }});
</script>
</body>
</html>
"""


def main() -> None:
    all_results = run_pipeline()
    if not all_results:
        print("No recipes found -- nothing to render.")
        return
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(render_html(all_results), encoding="utf-8")
    print(f"wrote {DOCS_DIR / 'index.html'}")


if __name__ == "__main__":
    main()

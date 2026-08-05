"""Runs the LLM judge over every cached extraction run and writes eval/judge_scores/*.json,
in the same run_id-keyed shape as eval/scores/ so the two are directly comparable.

Usage: .venv/Scripts/python.exe eval/run_judge.py [--model claude-sonnet-5] [--fresh]
Costs real money (judge calls hit the Anthropic API) unless everything's already cached
from a prior run -- rerunning with the same model/taxonomy is free.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from build_site import RECIPES, RUNS  # noqa: E402
from recipe_parser import is_cached, parse_recipe  # noqa: E402

from judge import judge_run  # noqa: E402

JUDGE_SCORES_DIR = Path(__file__).resolve().parent / "judge_scores"


def main(judge_model: str = "claude-sonnet-5", use_cache: bool = True) -> None:
    JUDGE_SCORES_DIR.mkdir(exist_ok=True)
    total_cost = 0.0
    n = 0

    for recipe in RECIPES:
        if not recipe["input"].exists():
            continue
        for provider, model, label in RUNS:
            run_id = f"{recipe['id']}__{provider}-{model}"
            if not is_cached(recipe["input"], provider, model):
                print(f"skipping {run_id}: extraction not cached -- run build_site.py first")
                continue
            extraction = parse_recipe(recipe["input"], provider, model, use_cache=True)

            result = judge_run(recipe["input"], extraction.title, extraction.nodes, model=judge_model, use_cache=use_cache)
            total_cost += result.estimated_cost_usd
            n += 1
            n_flagged = len(result.cell_flags)
            print(
                f"{run_id:45} judged | {n_flagged:2} nodes flagged | "
                f"${result.estimated_cost_usd:.4f} | {result.latency_s:5.1f}s"
            )

            out_path = JUDGE_SCORES_DIR / f"{run_id}.json"
            payload = {
                "run_id": run_id,
                "judge_model": judge_model,
                "cell_flags": result.cell_flags,
                "missing_flags": result.missing_flags,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n{n} runs judged, total cost ${total_cost:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-sonnet-5", help="judge model (Anthropic only for now)")
    parser.add_argument("--fresh", action="store_true", help="bypass the judge cache and re-call the API")
    args = parser.parse_args()
    main(judge_model=args.model, use_cache=not args.fresh)

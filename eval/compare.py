"""Compares eval/judge_scores/*.json against eval/scores/*.json (John's human baseline)
and reports per-tag precision/recall, so we can see which taxonomy dimensions a cheap
automated judge can be trusted on vs. which still need a domain expert.

Usage: .venv/Scripts/python.exe eval/compare.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from taxonomy import JUDGE_TAG_KEYS, MISSING_KEYS  # noqa: E402

SCORES_DIR = Path(__file__).resolve().parent / "scores"
JUDGE_SCORES_DIR = Path(__file__).resolve().parent / "judge_scores"


def _load_dir(d: Path) -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*.json"))}


def main() -> None:
    human = _load_dir(SCORES_DIR)
    judge = _load_dir(JUDGE_SCORES_DIR)
    run_ids = sorted(set(human) & set(judge))
    missing_runs = sorted(set(human) - set(judge))
    if missing_runs:
        print(f"({len(missing_runs)} runs have no judge score yet -- run eval/run_judge.py. Comparing the other {len(run_ids)}.)\n")

    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()

    cell_tp = cell_fp = cell_fn = 0

    for run_id in run_ids:
        h_flags = human[run_id]["cell_flags"]
        j_flags = judge[run_id]["cell_flags"]

        # layout_bug is structurally unjudgeable from the raw graph (see taxonomy.py) --
        # exclude it from the human side so it can't count as a guaranteed judge miss.
        h_flags = {node_id: [t for t in tags if t != "layout_bug"] for node_id, tags in h_flags.items()}
        h_flags = {node_id: tags for node_id, tags in h_flags.items() if tags}

        all_nodes = set(h_flags) | set(j_flags)
        for node_id in all_nodes:
            h_tags = set(h_flags.get(node_id, []))
            j_tags = set(j_flags.get(node_id, []))
            for tag in JUDGE_TAG_KEYS:
                in_h, in_j = tag in h_tags, tag in j_tags
                if in_h and in_j:
                    tp[tag] += 1
                elif in_j and not in_h:
                    fp[tag] += 1
                elif in_h and not in_j:
                    fn[tag] += 1
            # Coarse cell-level agreement: did they flag this node at all, regardless of tag?
            if h_tags and j_tags:
                cell_tp += 1
            elif j_tags and not h_tags:
                cell_fp += 1
            elif h_tags and not j_tags:
                cell_fn += 1

        # Whole-run missing-item checklist, same TP/FP/FN treatment.
        for key in MISSING_KEYS:
            in_h = bool(human[run_id]["missing_flags"].get(key))
            in_j = bool(judge[run_id]["missing_flags"].get(key))
            tag = f"missing:{key}"
            if in_h and in_j:
                tp[tag] += 1
            elif in_j and not in_h:
                fp[tag] += 1
            elif in_h and not in_j:
                fn[tag] += 1

    def prf(t: int, f_p: int, f_n: int) -> tuple[float, float]:
        precision = t / (t + f_p) if (t + f_p) else float("nan")
        recall = t / (t + f_n) if (t + f_n) else float("nan")
        return precision, recall

    print(f"{'tag':20} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>8}")
    print("-" * 58)
    for tag in [*JUDGE_TAG_KEYS, *[f"missing:{k}" for k in MISSING_KEYS]]:
        t, f_p, f_n = tp[tag], fp[tag], fn[tag]
        if not (t or f_p or f_n):
            continue
        precision, recall = prf(t, f_p, f_n)
        print(f"{tag:20} {t:>4} {f_p:>4} {f_n:>4} {precision:>10.2f} {recall:>8.2f}")

    print("-" * 58)
    precision, recall = prf(cell_tp, cell_fp, cell_fn)
    print(f"{'(any tag, cell-level)':20} {cell_tp:>4} {cell_fp:>4} {cell_fn:>4} {precision:>10.2f} {recall:>8.2f}")
    print(
        "\nprecision: of what the judge flagged, how much did the human agree with"
        "\nrecall:    of what the human flagged, how much did the judge catch"
    )


if __name__ == "__main__":
    main()

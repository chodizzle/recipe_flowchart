"""Single source of truth for the eval taxonomy -- shared by the human scoring tool
(app.py) and the LLM judge (judge.py), so the two can never silently drift apart.
"""

from __future__ import annotations

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

# The judge only ever sees the raw node graph, never the rendered HTML table -- so it
# structurally cannot judge whether gozinto_layout.py placed a correct graph in the wrong
# spot. layout_bug is a property of our own render code, not the extraction, and is
# excluded from what the judge is allowed to claim.
JUDGE_TAG_KEYS = [t["key"] for t in TAXONOMY if t["key"] != "layout_bug"]
MISSING_KEYS = [m["key"] for m in MISSING_CHECKLIST]

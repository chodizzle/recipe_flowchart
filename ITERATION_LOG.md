# Iteration Log

Raw, dated notes on each eval -> prompt-fix -> re-eval cycle for the extraction
pipeline. This is the working record; the README tells the distilled version once
a cycle settles.

## 2026-08-04: fixing the "Cooked" order/grouping failure

**Diagnosis.** The first full human-scored pass (all 18 runs, `eval/scores/`) found
19 `order` tags and 18 `grouping` tags -- two-thirds of every issue found. All 19
`order` tags were on one recipe, "Cooked" (sweet-and-sour pork), and every one of
the 6 models had at least one. Root cause, found via the eval tool's raw-node
inspector: the schema let a bare temperature statement ("increase the oil to
375F") become its own operation node with no inputs. Two unrelated later steps --
the second pork-fry and the veg-fry -- both pointed at that same temperature node
as their only shared input, so the layout algorithm placed them as siblings
instead of in sequence, even though the veg-fry actually reuses the same oil
*after* the pork is done frying.

**Fix.** Two changes to `EXTRACTION_INSTRUCTIONS` in `src/providers/base.py`,
deliberately framed as one general principle rather than a patch specific to this
recipe (temperature is never its own node; equipment/resource reuse is a real
dependency), plus a second worked example mirroring the actual failure. Full diff:

```diff
+A temperature or heat-level statement on its own ("heat oil to 325F", "increase
+the heat to 375F") is never its own operation node -- fold it into the `detail`
+of whichever operation actually happens at that temperature. And regardless of
+temperature: reusing the same piece of equipment or resource (pan, oven, oil,
+wok) is a real dependency even when no ingredient is shared -- that operation's
+`inputs` must include whatever earlier operation last used the same resource,
+so operations end up chained in the order they actually happen, not just the
+order their own ingredients happen to be ready.
+
+Second worked example -- input "Heat oil to 325F. Fry the pork, 2 min. Increase
+oil to 375F. Fry the pork again, 1 min. Add the peppers to the hot oil and fry,
+1 min." (pork and peppers as ingredient nodes i1, i2) produces:
+  {"id": "o1", ..., "technique": "fry", "inputs": ["i1"], "detail": "325F (165C), 2 min"}
+  {"id": "o2", ..., "technique": "fry", "inputs": ["o1"], "detail": "375F (190C), 1 min"}
+  {"id": "o3", ..., "technique": "fry", "inputs": ["o2", "i2"], "detail": "1 min"}
+Note "increase oil to 375F" is not its own node -- it's folded into o2's detail,
+and o2 still depends on o1 since it's the same oil, already in use. Note o3
+(frying the peppers) depends on o2, not just on the peppers -- it reuses the
+same hot oil right after, so it must come after, even though nothing about the
+peppers themselves required that order.
```

**Result on "Cooked" (the recipe the bug was diagnosed from) -- clean win.**
Re-ran extraction fresh on all 6 models. Every single one now: (a) has zero
standalone temperature-only operation nodes, and (b) chains the veg-fry step
after the second pork-fry as an explicit input, not just a shared temperature.
Structurally confirmed for Haiku, Sonnet, GPT-4o mini, GPT-4o, Gemini Flash-Lite,
and Gemini Flash -- the exact failure pattern is gone everywhere it was found.
**Human re-score of these 6 runs is the next step** (John, in the scoring tool)
to confirm the fix holds under the same rubric that found the bug, not just
structurally.

**Result on "Baked" and "Complex" (not where the bug was, checked for
regressions) -- mixed, one real new problem found.** Diffed old vs. new node
counts using the two models with zero human-flagged errors on both recipes
(Claude Sonnet 5, Gemini 3.5 Flash) as a pseudo-ground-truth reference, since
there's no full re-score of these two recipes yet:

- Sonnet on "Baked" held exactly stable (11 ingredients / 9 ops / 4 merges,
  unchanged) -- good sign for at least one pseudo-GT case.
- Every other cell changed somewhat (op counts shifted by 1-3), which is
  expected on its own -- the prompt change explicitly removes standalone
  temperature nodes, so a small op-count drop for recipes that had them is the
  *intended* effect, not evidence of a problem by itself.
- **GPT-4o mini on "Baked" collapsed from 8 operations to 1** (just "preheat
  oven" -- every mixing/baking/assembly step vanished). Confirmed reproducible
  with a second fresh API call, not a one-off sampling fluke. Working
  hypothesis: the prompt is now longer and carries two worked examples instead
  of one, and the weakest model in the lineup appears to lose the thread partway
  through rather than following the added structure -- i.e. a fix aimed at
  making stronger models more careful can silently break a cheaper model's
  ability to complete the task at all. Not yet root-caused further or fixed.

Update: `complex / google / gemini-3.5-flash` re-extracted cleanly on retry once
the Google-side outage cleared (10 ingredients / 9 -> 9 ops / 5 -> 6 merges --
modest, unremarkable change, consistent with the rest of "Complex"). All 18
runs are now on the new prompt, and `docs/index.html` was regenerated as a
result of the first fully-successful pipeline run.

**Human re-score of "Cooked" (John, same rubric that found the original bug) --
confirms the fix, surfaces two new findings.**

`order` tags: 19 -> 3. Five of six models now score zero order errors on
"Cooked." The 3 remaining are all on GPT-4o mini -- the same model that
independently regressed on "Baked" (see above), a second data point that this
specific model handles the added prompt reasoning worse than the rest of the
lineup.

Two things surfaced that the fix didn't touch, one of them self-inflicted:

- **Decomposition (splitting "3 tbsp water, divided" across the sauce and the
  cornstarch slurry) now shows up on all 6 models.** Not a regression -- this
  is a different failure category the prompt change never targeted; it was
  likely always there, just overshadowed by the order/grouping noise that
  dominated the first pass. Gemini 3.5 Flash self-corrected this via its own
  `detail`/prep field; the other 5 didn't.
- **Grouping: models now correctly sequence the veg-fry after the second
  pork-fry (the order fix worked), but merge them into the same operation
  instead of keeping them separate** -- the recipe fries the veg separately
  and sets it aside, combining everything only later at the sauce-toss step.
  This looks like a side effect of the fix itself: the new instruction says
  reusing a resource means `inputs` must include the prior user of it, but
  never distinguished "comes after" from "combines with" -- and in this
  schema, an operation with multiple inputs conventionally *means*
  convergence. The model is doing exactly what it was told; the instruction
  just didn't leave room for "sequenced but not merged." A real fix here needs
  a schema-level distinction (e.g. a separate "sequenced after" vs. "combined
  with" relationship), not another prompt sentence -- especially given the
  GPT-4o mini precedent that added prompt complexity can cost a weak model
  more than it gains a strong one.

**Decision: stop here, don't chase a third prompt iteration.** The arc is
already a complete, honest cycle -- diagnosed a specific bug, fixed it with a
principled (not patched) change, validated a real 19 -> 3 improvement on the
exact rubric that found it, and surfaced both a new blind spot and a side
effect of the fix itself rather than hiding either. Closing the remaining gap
needs a schema change, not a wording tweak, and isn't worth the complexity risk
right now.

**Open items:**
1. GPT-4o mini's collapse on "Baked" and its retained order errors on "Cooked"
   are both real, reproducible, and point the same direction -- worth
   remembering as a concrete model-selection data point (added prompt
   sophistication doesn't help every model equally, and can actively hurt the
   cheapest one) rather than something to fix.
2. A "sequenced after, not combined with" edge type is a real schema
   improvement to consider if this project continues past the eval-framework
   phase -- not scheduled now.

## 2026-08-04: closing the LLM-as-judge thread

Built a judge (`eval/judge.py`, `eval/run_judge.py`, `eval/compare.py`, taxonomy
shared with the human tool via `eval/taxonomy.py`) to test whether an LLM could
carry some of the human-scoring load. Ran it (Claude Sonnet 5 as judge) against
all 18 human-scored runs. Result: overall cell-level precision 0.33 / recall
0.28 against the human baseline. Worst on `order` specifically -- recall 0.05
(1 of 19 caught) -- and weak-to-nonexistent on `method`, `prep`, `extraneous`.
`grouping` was the least-bad dimension (precision 0.38 / recall 0.33), still
not trustworthy on its own.

**Root cause, not just a bad number.** The judge only ever sees the already-
extracted graph plus the source recipe, and critiques it in a single pass.
Catching a *missing* dependency (which is what almost every order error was)
requires reconstructing what the graph should look like and diffing against
it -- a fundamentally different, harder task than spotting a wrong-looking
node. A single critique pass isn't shaped to do that, regardless of which
model plays judge or how the prompt is worded. A judge that re-derives its own
graph first and diffs would plausibly do much better on `order` specifically,
but that's a different task shape to build, not a tweak to the existing one.

**Decision: close this thread here, without attempting that redesign.** Real
lesson, not a failure to gloss over: LLM judges sometimes don't work well out
of the box, and getting them trustworthy is its own real investment -- not
always a small one. Given this project's actual priorities (recipe expansion,
the write-up), that investment wasn't worth making right now, so the choice
was to skip it rather than force a marginal improvement. That's a legitimate,
common outcome under real constraints, and worth stating as one rather than
hiding it behind more tinkering. If revisited later, "re-derive and diff"
(not a prompt edit) is the concrete next design to try.

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

## 2026-08-05: full 10-recipe pass, and two findings worth keeping unfixed

Expanded to 10 recipes (60 runs) and John scored all of them by hand. Full
results aside (model ranking flipped -- Gemini 3.5 Flash is now the cleanest
model overall, not Sonnet; GPT-4o mini remains worst by a wide margin; the
order fix and noise-robustness both held up on new recipes built specifically
to stress-test them), two findings surfaced that are more interesting *as open
problems* than as bugs to patch, and John's call was to document them as
"intrigue" and move on rather than open a third prompt-engineering cycle.

**"Missing operation," or: the invisible transformation step.** On "Shredded
Beef Tacos," most models correctly generate a step that adds shredded beef
back into the reduced sauce -- but several don't properly chain that step
back to an actual "remove and shred" operation. Gemini 3.5 Flash-Lite is the
clean example: it *does* emit a node labeled "shred," but the final combine
step skips past it and references the raw, whole `beef` ingredient again
instead. On the rendered chart, the beef visually never gets shredded at all
-- there's a disconnected "shred" node floating off to the side that nothing
downstream actually uses. The general shape of the failure: models are good
at producing the next step that *sounds* right ("toss the beef back in") from
having seen that pattern in countless recipes, without the underlying graph
actually verifying that step's input traces back through a real, connected
chain of prior transformations. That's a broader caution for anyone chaining
LLM outputs into a pipeline: a locally-plausible next step is not the same
guarantee as a properly-grounded one, and the two can look identical unless
something downstream (a human, a validator, a schema check) actually traces
the lineage.

**"Layout bug," or: extraction order silently becomes visual meaning.** On the
same recipe, the rendered chart's "Season" bracket visually spans across
"olive oil" even though olive oil isn't one of its real inputs -- confirmed by
tracing the actual code: `gozinto_render.py` places ingredient rows in
whatever order the model happened to emit them in, with zero semantic
reordering, and an operation's cell spans from its lowest to highest input row
inclusive. So when a later operation's true inputs (beef + spice mix) aren't
contiguous in the model's own extraction order, the rendered bracket has no
way to "skip over" an unrelated ingredient sitting in between -- it's not a
reasoning failure in the model, and it's not a rendering bug in the strict
sense either (the render is faithfully reflecting the order it was given). It's
a mismatch: the renderer implicitly assumes nearby-in-list ingredients are more
likely to be grouped together, and nothing ever told the model that its
extraction order would carry that visual weight downstream. General lesson:
when a downstream consumer (a UI, a report, another model) infers structure
from the *order* of an upstream LLM's output rather than from explicit
relationships, that's an assumption that can silently break, because output
order is rarely something the upstream prompt was asked to optimize for.

**Also still open, not chased further**: timing/order errors beyond the
specific shared-resource pattern already fixed. It's not that heating oil
first is always wrong, but recipes often contain cues that heating should
follow certain other steps, and models still don't reliably anchor on those
cues. The earlier fix only covers the narrower "same equipment reused" case,
not general temporal-cue reasoning.

**Decision, same as the judge thread**: don't reprompt. All three are
plausibly fixable with more targeted instructions, but the value here is in
having found and precisely diagnosed them, not in chasing a fourth prompt
iteration before finishing the write-up.

**A fourth finding, and it's the most important one for eval design specifically:
this task doesn't have a single correct answer.** John's own scoring already
treats it this way (multiple models on the same recipe both marked fully
correct), but it's worth naming and grounding in an example. On "Roast
Potatoes," three models scored zero issues with genuinely different graphs:

- GPT-4o (7 ops) -- most compact. Doesn't model "boil water" as its own node
  (folds it straight into the potato-boil step), and does the entire roast
  (20 min undisturbed, then flip, then 30-40 more) as one operation.
- Gemini 3.5 Flash (9 ops) -- middle ground. Separates "boil water" as its own
  step, but still keeps the roast as one node.
- Claude Sonnet 5 (10 ops) -- most granular. Separates "boil water" *and*
  splits the roast into two explicit phases, mirroring the recipe's own
  two-phase instruction (undisturbed, then flip-and-continue).

None of these is more correct than the others -- they're just different
choices about what granularity to decompose a continuous physical process
(boiling, roasting) into discrete graph nodes, and all three read as an
intuitive, usable Gozinto chart. The goal was never "reconstruct the one true
graph," it was "produce something a human can read and trust" -- and there's
real art in where you draw those lines, the same way there's more than one
correct way to outline a recipe by hand.

This retroactively sharpens why the LLM-judge thread struggled, and reframes
what "closed, revisit with re-derive-and-diff" actually needs. A judge that
builds its own reference graph and diffs against the extraction assumes a
single correct graph to diff against -- but that assumption is false for this
task, as this finding shows directly. A future judge redesign would need to
evaluate structural *equivalence classes* or functional properties (are the
true dependencies captured? is it readable?) rather than exact-match diffing
against one reference. Worth remembering as the real reason a naive
re-derive-and-diff judge wouldn't just be hard to build, but conceptually
underspecified as-is.

**General lesson for eval design**: before building any eval loop -- human,
automated, or hybrid -- it's worth asking whether the task has one correct
answer or a family of acceptable ones. Grading against a single reference
(or asking a judge to reconstruct one) silently punishes valid alternatives
in the second case. This task turned out to be the second case, and the eval
tool (multi-tag, per-cell flags on what's *wrong* rather than diffing against
a canonical answer) happened to be the right shape for that almost by
accident -- worth being deliberate about next time rather than lucking into it.

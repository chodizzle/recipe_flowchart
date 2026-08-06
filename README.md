# Recipe Flowchart

An end-to-end example of the pattern I actually use at work: find a task that used to require brittle hand-coded parsing, replace it with an LLM, and treat "how do I know it's actually right" as a first-class engineering problem rather than an afterthought.

The task here is turning a recipe into a **Gozinto chart** (an industrial-engineering assembly diagram: ingredients converge through operations into a finished dish, read left to right) — structuring unstructured text used to mean regex and endless if-chains, and LLMs do it directly now. But "can a model do this" turned out to be the boring question. The interesting one, and the actual point of this project, is: **there's no ground-truth dataset for "is this Gozinto chart correct" — only a domain expert's judgment (mine; I was a chef before I was a data analyst).** So this project is really a worked example of building a rigorous eval loop when the only available ground truth is a human, not a benchmark: structure the extraction task, build a way to score it, find real bugs, fix them with targeted (not shotgun) changes, validate the fix against the same rubric that found the bug, and be honest in writing about the things that didn't get fixed.

## What it does

1. **Input**: recipe text or a photo (including handwritten notes)
2. **Extraction**: one forced tool-use / function-calling request per model returns a title plus a flat list of nodes — `ingredient` nodes (name, amount, always a leaf) and `operation` nodes (a short technique label plus `inputs`, the ids of whatever it consumes). `inputs` points backward at what feeds in, so the whole dependency graph falls out of one field per node, no separate step numbering
3. **Table generation**: the graph is layered (an operation's column is 1 + the deepest layer of its own inputs) and rendered as a plain server-side HTML `<table>`, `rowspan` merging every ingredient row that feeds a shared operation into one bracket-shaped cell — no client-side library at all
4. **Model comparison**: the same 10 recipes run against Claude Haiku 4.5, Claude Sonnet 5, GPT-4o mini, GPT-4o, Gemini 3.5 Flash-Lite, and Gemini 3.5 Flash (60 runs total), and the public site shows cost, latency, and structure side by side
5. **Human eval**: every one of those 60 runs is scored by hand, against a fixed taxonomy, in a local scoring tool built for exactly this (`eval/app.py`) — see [The eval problem](#the-eval-problem) below

Since GitHub Pages can't run a live backend, the public comparison site is pre-generated: `src/build_site.py` runs the pipeline locally and bakes the results into a static `docs/index.html`. No API key ever reaches the browser. The eval tool is local-only and never gets deployed — it writes real annotation data to disk, which isn't something a static page can do.

## The eval problem

There's no dataset of "correctly structured Gozinto charts" to check against, and building one by hand for every recipe would just relocate the problem — who verifies the verifier? The only real ground truth available is a domain expert reading the output and judging whether it's actually right, the same way a chef would look at a written recipe and know if the steps were out of order.

That judgment needed a rubric, not vibes, so the scoring tool (`eval/app.py`, `eval/taxonomy.py`) is built around one rule: **click a cell, tag it from a fixed taxonomy, no free text.** Every flagged cell gets one or more of `decomposition`, `grouping`, `method`, `prep`, `timing`, `order`, `extraneous`, or one of two fault-attribution tags — `layout_bug` and `ambiguous_source` — that mean "flag it, but don't count it against the model" for a different reason each (our own rendering code vs. an unclear source). A separate whole-run checklist covers the cases that don't have a cell to click at all (something that never made it into the graph). The popover also shows the clicked node's actual `inputs`, resolved to real ingredient names — so "does this look wrong" turns into "is this specific dependency actually wrong," checkable against the real data instead of guessed at from the rendering.

**The sharpest finding from using this tool isn't about any one model — it's that the task itself doesn't have a single correct answer.** On "Roast Potatoes," three different models scored fully clean with genuinely different graphs: GPT-4o (7 operations) folds "boil water" into the potato-boiling step and treats the whole roast as one operation; Gemini 3.5 Flash (9 operations) separates out "boil water" but still keeps the roast as one step; Claude Sonnet 5 (10 operations) does both, splitting the roast into its two real phases (undisturbed, then flip-and-continue) to mirror the recipe's own two-phase instruction. None of these is more correct than the others — they're different, equally valid choices about what granularity to decompose a continuous physical process into. The goal was never "reconstruct the one true graph," it was "produce something a human can read and trust," and there's real art in where those lines get drawn. That's worth knowing *before* building an eval loop, not after: grading against a single reference (or asking an automated judge to reconstruct one) would silently punish valid alternatives for a task shaped like this one. Full write-up of this and the tool's design decisions, warts included, is in [ITERATION_LOG.md](ITERATION_LOG.md).

## The 10 recipes

Three from the original pass, seven added later specifically to stress-test findings from the first round rather than just to pad the count:

- **Cooked** (Serious Eats, Chinese Sweet and Sour Pork) — marinate, dredge, double-fry the pork, fry the vegetables, and make the sauce, largely independent tracks that converge in one final toss. This is the recipe that broke every single model on sequencing (see below).
- **Baked** (NYT Cooking, Spinach Egg Bites) — mostly linear, but heating the oven, greasing the tin, and mixing the batter are genuinely independent until the fill step.
- **Handwritten** (my own kitchen notes, Choux au Craquelin) — a photo of bilingual Korean/English shorthand with hand-drawn brackets, to stress-test the vision-extraction path.
- **Web Scrape** (Serious Eats, roast potatoes) — pasted with all the real noise a scraped recipe page actually has: a testing-methodology essay, table of contents, image captions, "Special Equipment," "Notes." Also has a genuine parallel step ("Meanwhile, combine olive oil...") to check whether a later fix (below) would overcorrect and force a false dependency on independent branches.
- **Pancakes** (Serious Eats) — eggs get separated into whites and yolks, processed on two different paths, then folded back together.
- **Eggnog** (Alton Brown) — eggs get separated too, but here only the yolks continue into the recipe; the whites are explicitly set aside for something else and never used.
- **Mac & Cheese** (Food Network, Alton Brown) — the simplest recipe in the set, 2 directions, included as a control.
- **Potstickers** (Damn Delicious) — a two-stage single-step cook (crisp, then add water and steam) and an assembly step where filling gets enclosed in a wrapper rather than just mixed.
- **Shredded Beef Tacos** (RecipeTin Eats) — a "Tacos" serving section references toppings (tortillas, avocado, sour cream) that were never in the stated ingredient list, to check whether models hallucinate amounts for things they were never told, or correctly leave them out.
- **Tikka Masala** (Savory Tooth) — sauté, pressure-cook, and finish, all in the same pot, structurally almost identical to the exact bug found in "Cooked" — added specifically to check whether the fix for that bug actually generalized to a new recipe, or was overfit to the one it was diagnosed from.

## Results

60 runs (10 recipes x 6 models), $0.74 total, cached to disk after the first pass so re-running is free unless the recipe, prompt, schema, or sampling settings change.

| Model | Total cost (10 recipes) | Avg latency | Human-flagged issues (60 runs, lower is better) |
|---|---:|---:|---:|
| Gemini 3.5 Flash | $0.1327 | 23.2s | **7** |
| Claude Sonnet 5 | $0.3370 | 10.9s | 10 |
| Gemini 3.5 Flash-Lite | $0.0332 | 3.0s | 12 |
| GPT-4o | $0.1306 | 5.8s | 18 |
| Claude Haiku 4.5 | $0.0895 | 5.8s | 23 |
| GPT-4o mini | $0.0128 | 9.9s | 33 |

Full per-recipe, per-model breakdown (cost, latency, tokens, structure) is on the [live site](https://chodizzle.github.io/recipe_flowchart/), regenerated from the same cache as this table.

Note the shape of that table: the cheapest model (GPT-4o mini) is also the worst by a wide margin, but the most expensive model (Sonnet) isn't the best — Gemini 3.5 Flash, priced in between, is. Price tier doesn't predict quality here in either direction.

## What I learned

### The order/grouping bug that broke every model on one recipe, and the fix that held up
The first full human-scored pass (18 runs, 3 recipes) found 19 `order` tags and 18 `grouping` tags — two-thirds of every issue found, and all 19 order errors on one recipe, "Cooked," with every model getting it wrong. Root cause, found via the eval tool's raw-node inspector: the schema let a bare temperature statement ("increase the oil to 375F") become its own operation node with no inputs, so two unrelated later steps (frying the pork a second time, then frying the vegetables) both pointed at that shared temperature node instead of chaining after each other — even though the veg-fry actually reuses the same oil right after the pork.

Fixed with one targeted, general instruction rather than a patch specific to this recipe: temperature is never its own node, and reusing the same equipment or resource is a real dependency even without a shared ingredient. Re-scored against the same rubric that found the bug: order tags on "Cooked" dropped from 19 to 3, with the 3 remaining all on GPT-4o mini. Validated two ways beyond that recipe: "Tikka Masala," added later specifically because it has the same same-pot-reused-across-steps shape, came back with only 5 total issues; and "Roast Potatoes," which has a genuinely parallel step, showed the fix didn't overcorrect — the oil-infusion step correctly kept its inputs to just the raw ingredients, with zero false dependency on the unrelated potato-boiling step, across all 6 models.

### Fixing one thing can surface (or cause) others, and that's worth writing down too
The order fix didn't come free. Two things showed up in the re-score that weren't there before, in the same recipe: a decomposition gap (splitting "3 tbsp water, divided" across two later steps) now visible on all 6 models, likely just no longer overshadowed by the order noise that dominated the first pass; and a grouping side effect of the fix itself — models now correctly sequence the veg-fry after the pork-fry, but merge them into one operation instead of keeping them separate, because the new instruction taught "reusing a resource means it's a real input" without distinguishing "comes after" from "combines with," and this schema's `inputs` field conventionally implies the latter. That's not a failure to hide; a real fix needs a schema-level distinction, not another prompt sentence, and isn't worth the complexity risk given a prior regression (below) from a similar kind of change.

### Recurring, harder-to-fix pattern: ingredients that split into derived sub-parts
Four separate recipes hit a version of the same gap: Cooked's reserved marinade, Cooked's divided water, Eggnog's separated-and-abandoned egg whites, Pancakes' separated-and-recombined eggs. The schema can say "this operation consumes this ingredient," but has no way to say "this ingredient splits into distinct derived parts that get used differently" — so models either reuse the same ingredient node twice (implying double consumption) or lose track of the split. Four independent examples across three different recipe styles makes this a real, structural gap, not noise from one odd recipe.

### Two more structural findings, deliberately left unfixed
Documented as "intrigue" rather than chased with a fourth prompt-engineering pass, since the value was in precisely diagnosing them, not in solving every last thing before finishing this write-up:
- **Invisible transformation steps.** On "Shredded Beef Tacos," several models generate a step that references shredded beef going back into the sauce without properly chaining back to an actual "remove and shred" operation — Gemini 3.5 Flash-Lite creates a `shred` node, then has the final combine step reference the raw, whole beef ingredient again instead, so the beef visually never gets shredded at all on the rendered chart. The general shape: a model can produce a next step that *sounds* right from having seen the pattern in countless recipes, without the underlying graph actually verifying that step traces back through a real, connected chain — a caution worth keeping in mind for anyone chaining LLM outputs into a pipeline more broadly.
- **Extraction order becoming visual meaning.** On the same recipe, the rendered chart visually spans a "Season" bracket across "olive oil," which isn't actually one of its inputs. Traced directly in the code: `gozinto_render.py` places ingredient rows in whatever order the model happened to emit them, with zero semantic reordering, and an operation's cell spans from its lowest to highest input row inclusive. Not a rendering bug in the strict sense (the render faithfully reflects the order it was given) and not a model reasoning error either — it's a mismatch, since nothing ever told the model that its extraction order would carry visual weight downstream.

### An LLM judge was tried, and closed as a real "not worth it right now" call
Built a second LLM to score extractions against the same taxonomy John used by hand (`eval/judge.py`), to see if it could reduce the human scoring load. Result against the human baseline: 0.33 precision / 0.28 recall overall, and 0.05 recall on `order` specifically — it caught 1 of 19 order errors. Root cause: catching a *missing* dependency requires reconstructing what the graph should look like and diffing against it, which a single critique pass isn't shaped to do, regardless of model or prompt wording. Retroactively, the "no single correct answer" finding above sharpens this further — a judge that builds its own reference graph and diffs against the extraction would still assume a single correct graph exists to diff against, which this project's own eval data shows isn't true for this task. Closed rather than iterated on: getting an LLM judge trustworthy is its own real investment, and given this project's actual priorities, that investment wasn't worth making right now. That's a legitimate, common outcome under real constraints, not a failure to gloss over.

### A "required" schema field isn't actually required
Claude Sonnet 5 silently omits the `title` field — marked `required` in the JSON schema — on 9 of the 10 recipes, while every other model gets it right essentially every time. This held even at `temperature=0`, so it isn't sampling noise, and the tell is that Sonnet gets `title` right on the four-node worked example in the prompt and only drops it once the node list grows into the dozens — a field it clearly "knows" to fill, dropped under output-length pressure once forced tool-use has a large array to focus on. `build_site.py` falls back to any other run's title rather than trusting one model's output blindly. Schema-conformant isn't the same guarantee as schema-complete, on either provider — the OpenAI side had its own version of this same lesson (next finding).

### A "strict" mode that wasn't actually strict
Scaling to 10 recipes surfaced a real bug: GPT-4o mini crashed extracting "Potstickers" with a node missing `id` entirely. Turned out OpenAI's strict structured-output mode, which is supposed to guarantee every `required` field is present, was never actually enabled — it needs both `strict: true` on the tool definition and `additionalProperties: false` on every object in the schema, and neither was set, so the schema's `required` list was never truly enforced despite a code comment claiming it was. Fixed in `openai_provider.py` without mutating the shared schema used by the other providers. The lesson generalizes past this one bug: a documented guarantee ("strict mode enforces required fields") can be silently inert if you don't check every precondition the API actually needs for it to kick in, and it can take a harder or more diverse input to expose that gap after it's already shipped.

### Added prompt sophistication can help one model and break another
The same prompt fix that solved the order bug also caused GPT-4o mini's "Baked" extraction to collapse from 8 operations to 1 (just "preheat oven," every other step gone) — confirmed reproducible on a second fresh call, not sampling noise. Working theory: the prompt got longer and added a second worked example, and the weakest model in the lineup lost the thread rather than following the added structure. A concrete, real model-selection data point: making a prompt more thorough for the models that can use it isn't free for the ones that can't.

### One outlier tokenizer, not a provider-wide pattern
On the handwritten photo, five of six models land within a tight token band regardless of price tier — GPT-4o mini alone spikes to 37,690 input tokens, a ~19x outlier against every other model including its own sibling GPT-4o. Gemini's cheap tier handles the same photo as efficiently as GPT-4o's flagship, so this isn't "vision is expensive for cheap models" broadly — it's that this specific tokenizer has a real gap worth checking before assuming a price tier's text economics carry over to images.

### Forced tool-use removes the parsing problem, not the completeness problem
Every run across all 10 recipes and 3 providers' different function-calling implementations returned syntactically valid, schema-conformant JSON — no retries, no regex cleanup, no manual JSON repair. Turning unstructured text (or a photo of handwriting) into structured data used to be the hard part, and for this task, it no longer needs attention. What still needs attention, per several findings above, is whether the *content* inside that valid JSON is actually complete and correct — a different, harder problem that structured output alone doesn't solve.

## The eval tool

Local-only, never touches provider APIs (only reads what's already in `.cache/`), never deployed:

```bash
.venv/Scripts/python.exe eval/app.py
```

then open `http://127.0.0.1:5050`. Two-pane layout — recipe source on the left, rendered Gozinto on the right, each scrolling independently — click any cell to tag it from the fixed taxonomy, with the raw dependency data shown right in the popover. Every click writes immediately to `eval/scores/<run_id>.json`.

A companion judge tool exists (`eval/judge.py`, `eval/run_judge.py`, `eval/compare.py`) but is closed per the finding above, not part of the regular workflow.

## Stack

- Python, `anthropic`, `openai`, and `google-genai` SDKs: forced tool-use / function-calling extraction against a shared JSON schema, `temperature=0` (plus `seed` where supported) for as-deterministic-as-possible output (`src/providers/`)
- Flask + Jinja2: the local human-eval scoring tool (`eval/`)
- Plain server-rendered HTML/CSS (`src/gozinto_layout.py`, `src/gozinto_render.py`): DAG layering + `rowspan`-merged table, no client-side library at all
- A content-addressed on-disk cache (`src/recipe_parser.py`, `eval/judge.py`, `.cache/`, gitignored): re-running any pipeline is free unless the recipe, prompt, schema, or sampling settings actually changed
- Jupyter: dev notebook mirroring the pipeline (`notebook.ipynb`)

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your own `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GOOGLE_API_KEY` (free tier available from [Google AI Studio](https://aistudio.google.com/apikey)).

Regenerate the public comparison site:

```bash
python src/build_site.py          # cached, instant, free after the first pass
python src/build_site.py --fresh  # bypass cache, force real API calls
```

Run the human-eval scoring tool:

```bash
.venv/Scripts/python.exe eval/app.py
```

Full iteration-by-iteration history — every bug found, every prompt diff, every honest dead end — is in [ITERATION_LOG.md](ITERATION_LOG.md).

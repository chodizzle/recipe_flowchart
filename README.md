# Recipe Gozinto

This project turns a recipe into a **Gozinto chart**, an industrial-engineering diagram where ingredients flow through operations into a finished dish, read left to right. Structuring text like this used to mean writing parsing rules by hand. Now an LLM can just do it.

The real question isn't whether a model can do that. It's how you check whether the output is right. There's no dataset of "correctly structured Gozinto charts" to grade against, only a domain expert's judgment: mine, since I was a chef before I became a data analyst.

So this project is really about the second problem: how do you build a rigorous eval loop when the only ground truth is a person, not a benchmark? Recipes are just the worked example.

This repo has:

- An extraction pipeline: 6 models across 3 providers (Anthropic, OpenAI, Google) turn recipe text or photos into Gozinto charts
- A human eval tool with a fixed taxonomy, not free text, for scoring the output
- A real bug, found with that tool, fixed, and re-validated against the same rubric that caught it
- An LLM-judge experiment that didn't work, and the reason why
- A finding that this task doesn't have one correct answer, and what that means for building an eval loop at all

## What it does

1. **Input**: recipe text or a photo (including handwritten notes)
2. **Extraction**: one forced tool-use / function-calling request per model returns a title plus a flat list of nodes. `ingredient` nodes are leaves (name, amount). `operation` nodes have a short technique label plus `inputs`, the ids of whatever they consume. `inputs` points backward at what feeds in, so the whole dependency graph falls out of one field per node, no separate step numbering.
3. **Table generation**: each operation's column number is 1 plus the deepest column among its own inputs, so operations end up ordered by how many steps deep they are. Rendered as a plain server-side HTML `<table>`, with `rowspan` merging every ingredient row that feeds a shared operation into one bracket-shaped cell. No client-side library at all.
4. **Model comparison**: the same 10 recipes run against Claude Haiku 4.5, Claude Sonnet 5, GPT-4o mini, GPT-4o, Gemini 3.5 Flash-Lite, and Gemini 3.5 Flash (60 runs total). The public site shows cost, latency, and structure side by side.
5. **Human eval**: every one of those 60 runs is scored by hand, against a fixed taxonomy, in a local scoring tool built for exactly this (`eval/app.py`), covered next.

Since GitHub Pages can't run a live backend, the public comparison site is pre-generated: `src/build_site.py` runs the pipeline locally and bakes the results into a static `docs/index.html`. No API key ever reaches the browser. The eval tool is local-only and never gets deployed: it writes real annotation data to disk, which a static page can't do.

## The eval loop

There's no dataset of "correctly structured Gozinto charts" to check against. Building one by hand for every recipe would just move the problem: who verifies the verifier? The only real ground truth available is a domain expert reading the output and judging whether it's right, the way a chef reads a written recipe and knows if the steps are out of order.

That judgment needed a rubric, not vibes. The scoring tool (`eval/app.py`, `eval/taxonomy.py`) is built around one rule: click a cell, tag it from a fixed taxonomy, no free text. Every flagged cell gets one or more of `decomposition`, `grouping`, `method`, `prep`, `timing`, `order`, `extraneous`, or one of two fault-attribution tags, `layout_bug` and `ambiguous_source`, that mean "flag it, but don't count it against the model" for a different reason each (my own rendering code vs. an unclear source). A separate whole-run checklist covers cases that don't have a cell to click at all: something that never made it into the graph. The popover also shows the clicked node's actual `inputs`, resolved to real ingredient names, so "does this look wrong" becomes "is this specific dependency actually wrong," checkable against the real data instead of guessed at from the rendering.

A few things stood out from building and using this tool:

- **Eval tools are cheap to build now.** With an LLM doing the scaffolding, a taxonomy-driven scoring UI like this one is maybe an hour of work instead of a multi-day detour. That changes the calculus on human-in-the-loop eval: it's economical to build a real tool instead of skipping straight to spot-checking a few outputs by eye.
- **The task doesn't have one correct answer.** On "Roast Potatoes," three different models scored fully clean with genuinely different graphs (details below). Grading against a single reference, or asking an automated judge to reconstruct one, would silently punish valid alternatives for a task shaped like this.
- **The scored output pointed straight at the fix.** The first full pass surfaced one dominant failure mode (covered in [What Went Wrong, and What It Taught Me](#what-went-wrong-and-what-it-taught-me)), and because every flag was tied to a specific cell and tag, tracing it back to a root cause in the code took minutes, not guesswork. That's the actual payoff of a rubric-based tool: not just "here's a score," but "here's exactly what to go fix."

On "Roast Potatoes": GPT-4o (7 operations) folds "boil water" into the potato-boiling step and treats the whole roast as one operation. Gemini 3.5 Flash (9 operations) separates out "boil water" but still keeps the roast as one step. Claude Sonnet 5 (10 operations) does both, splitting the roast into its two real phases (undisturbed, then flip-and-continue) to mirror the recipe's own two-phase instruction. None of these is more correct than the others: they're different, equally valid choices about what granularity to decompose a continuous physical process into. The goal was never "reconstruct the one true graph," it was "produce something a human can read and trust," and there's real art in where those lines get drawn. Full write-up of this and the tool's design decisions, warts included, is in [ITERATION_LOG.md](ITERATION_LOG.md).

## The 10 recipes

Three from the original pass, seven added later specifically to stress-test findings from the first round rather than just to pad the count:

- **Cooked** (Serious Eats, Chinese Sweet and Sour Pork): marinate, dredge, double-fry the pork, fry the vegetables, and make the sauce, largely independent tracks that converge in one final toss. This is the recipe that broke every single model on sequencing (see below).
- **Baked** (NYT Cooking, Spinach Egg Bites): mostly linear, but heating the oven, greasing the tin, and mixing the batter are genuinely independent until the fill step.
- **Handwritten** (my own kitchen notes, Choux au Craquelin): a photo of bilingual Korean/English shorthand with hand-drawn brackets, to stress-test the vision-extraction path.
- **Web Scrape** (Serious Eats, roast potatoes): pasted with all the real noise a scraped recipe page actually has: a testing-methodology essay, table of contents, image captions, "Special Equipment," "Notes." Also has a genuine parallel step ("Meanwhile, combine olive oil...") to check whether a later fix (below) would overcorrect and force a false dependency on independent branches.
- **Pancakes** (Serious Eats): eggs get separated into whites and yolks, processed on two different paths, then folded back together.
- **Eggnog** (Alton Brown): eggs get separated too, but here only the yolks continue into the recipe; the whites are explicitly set aside for something else and never used.
- **Mac & Cheese** (Food Network, Alton Brown): the simplest recipe in the set, 2 directions, included as a control.
- **Potstickers** (Damn Delicious): a two-stage single-step cook (crisp, then add water and steam) and an assembly step where filling gets enclosed in a wrapper rather than just mixed.
- **Shredded Beef Tacos** (RecipeTin Eats): a "Tacos" serving section references toppings (tortillas, avocado, sour cream) that were never in the stated ingredient list, to check whether models hallucinate amounts for things they were never told, or correctly leave them out.
- **Tikka Masala** (Savory Tooth): sauté, pressure-cook, and finish, all in the same pot, structurally almost identical to the exact bug found in "Cooked," added specifically to check whether the fix for that bug actually generalized to a new recipe, or was overfit to the one it was diagnosed from.

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

The cheapest model (GPT-4o mini) is also the worst by a wide margin, but the most expensive model (Sonnet) isn't the best. Gemini 3.5 Flash, priced in between, is. Price tier doesn't predict quality here in either direction.

Gemini also wins on this task in my day-to-day work, not just in this test. I use Gemini (2.x and 3.x) for parsing and structuring tasks at work, and it's consistently strong at conforming to a JSON schema or Pydantic model. That matches a pattern a lot of people already assume: certain models are just better suited to certain jobs (Claude for coding is the other example people usually reach for). This project's results back that up rather than contradict it.

## What Went Wrong, and What It Taught Me

### Prompt engineering was the fastest fix, and probably should be your first move
The first full human-scored pass (18 runs, 3 recipes) found 19 `order` tags and 18 `grouping` tags: two-thirds of every issue found, all 19 order errors on one recipe ("Cooked"), every model getting it wrong. The eval tool's raw-node inspector pointed straight at the cause: the schema let a bare temperature statement ("increase the oil to 375F") become its own operation node with no inputs, so two unrelated later steps (frying the pork a second time, then frying the vegetables) both pointed at that shared temperature node instead of chaining after each other, even though the veg-fry actually reuses the same oil right after the pork.

The fix was one instruction added to the prompt: temperature is never its own node, and reusing the same equipment or resource is a real dependency even without a shared ingredient. Re-scored against the same rubric that found the bug, order tags on "Cooked" dropped from 19 to 3 (all 3 on GPT-4o mini). Validated two more ways: "Tikka Masala," added later because it has the same reused-pot shape, came back with only 5 total issues, and "Roast Potatoes," which has a genuinely parallel step, showed the fix didn't overcorrect: the oil-infusion step correctly kept its inputs to just the raw ingredients, with no false dependency on the unrelated potato-boiling step, across all 6 models.

When a model gets something wrong, there are a few ways to fix it: give it more or better context, fine-tune it, build a tool or skill around it, or just improve the prompt. Prompt engineering is almost always the cheapest of those to try first, and here it fixed a two-thirds-of-all-issues bug in one sentence.

### Prompt engineering has a cost, especially on smaller models
That same one-sentence fix caused GPT-4o mini's "Baked" extraction to collapse from 8 operations down to 1 (just "preheat oven," every other step gone), confirmed reproducible on a second fresh call, not sampling noise. It also introduced two smaller side effects in "Cooked" itself: a decomposition gap ("3 tbsp water, divided" splitting across two later steps) that's likely just no longer buried under the order noise from before, and a grouping side effect where the veg-fry and pork-fry now correctly sequence one after the other but get merged into a single operation instead of staying separate, since "reusing a resource is a real input" didn't distinguish "comes after" from "combines with."

None of this is free. A longer, more detailed prompt can help a strong model and actively confuse a weaker one: more tokens to track, more instructions competing for attention, and slower inference along the way. I've hit the same thing at work: a prompt tuned for a flagship model can quietly break a cheaper one further down the same pipeline. Check every model in the lineup after a prompt change, not just the one that motivated it.

### Structured input teaches models to stay structured
Three separate findings turned out to share one root cause: the ingredient list itself.

- **Ingredients that split into derived parts.** Four recipes hit a version of the same gap: Cooked's reserved marinade, Cooked's divided water, Eggnog's separated-and-abandoned egg whites, Pancakes' separated-and-recombined eggs. My hypothesis: the ingredient list is a strong, literal signal, and a model tracks it closely. Splitting one listed ingredient into two differently-used parts isn't something the list itself hints at, so models need to be told to do it, and mostly don't without that direction.
- **Invisible transformation steps.** On "Shredded Beef Tacos," several models generate a step that uses shredded beef without ever chaining back to a real "remove and shred" step: Gemini 3.5 Flash-Lite creates a `shred` node, then has the final combine step reference the raw, whole beef ingredient again instead, so the beef visually never gets shredded on the rendered chart. Same hypothesis: "cooked beef" isn't on the ingredient list, it's a mid-process product buried in the instructions, so the model doesn't track it as carefully as something it saw listed up front.
- **Extraction order becoming visual meaning.** On the same recipe, the rendered chart visually spans a "Season" bracket across "olive oil," which isn't actually one of its inputs. Traced in the code: `gozinto_render.py` places ingredient rows in whatever order the model emitted them, with no semantic reordering, and an operation's cell spans from its lowest to highest input row. The model emitted ingredients close to the order they were listed, not the order they were actually used, and that ordering choice became a visual bug once it hit the renderer.

The pattern across all three: the listed ingredients implicitly anchor the model. They discourage decomposition, make it easy to gloss over intermediate products that were never listed, and pull emitted order toward listing order instead of the order things actually happen. Overcoming it will probably take deliberate prompting, or a different fix entirely, not something that resolves on its own. Structure reinforces structure.

### An LLM judge was tried, and closed as a real "not worth it right now" call
Built a second LLM to score extractions against the same taxonomy I used by hand (`eval/judge.py`), to see if it could reduce the human scoring load. Result against the human baseline: 0.33 precision / 0.28 recall overall, and 0.05 recall on `order` specifically (it caught 1 of 19 order errors). Root cause: catching a *missing* dependency requires reconstructing what the graph should look like and diffing against it, which a single critique pass isn't shaped to do, regardless of model or prompt wording.

The "no single correct answer" finding above sharpens this further: a judge that builds its own reference graph and diffs against the extraction would still assume a single correct graph exists to diff against, and this project's own eval data shows that isn't true for this task. Closed rather than iterated on: getting an LLM judge trustworthy is its own real investment, and given this project's actual priorities, that investment wasn't worth making right now. That's a legitimate, common outcome under real constraints, not a failure to gloss over.

### A "required" field wasn't actually required (and Claude was the exception)
Claude Sonnet 5 silently omits the `title` field, marked `required` in the JSON schema, on 9 of the 10 recipes, while every other model gets it right nearly every time. This held even at `temperature=0`, so it isn't sampling noise. The tell: Sonnet gets `title` right on the four-node worked example in the prompt, and only drops it once the node list grows into the dozens, a field it clearly "knows" to fill, dropped under output-length pressure once forced tool-use has a large array to focus on. `build_site.py` falls back to any other run's title rather than trusting one model's output blindly.

Every model has its own quirks. Sonnet is the nonconformist here (schema-conformant isn't the same guarantee as schema-complete), and the OpenAI side had its own version of the same lesson, next.

### A "strict" mode that wasn't actually strict
Scaling to 10 recipes surfaced a real bug: GPT-4o mini crashed extracting "Potstickers" with a node missing `id` entirely. Turned out OpenAI's strict structured-output mode, which is supposed to guarantee every `required` field is present, was never actually enabled. It needs both `strict: true` on the tool definition and `additionalProperties: false` on every object in the schema, and neither was set, so the schema's `required` list was never truly enforced despite a code comment claiming it was. Fixed in `openai_provider.py` without mutating the shared schema used by the other providers.

A documented guarantee ("strict mode enforces required fields") can be silently inert if you don't check every precondition the API actually needs for it to kick in. It can take a harder or more diverse input to expose that gap after it's already shipped.

### One outlier tokenizer, not a provider-wide pattern
On the handwritten photo, five of six models land within a tight token band regardless of price tier. GPT-4o mini alone spikes to 37,690 input tokens, a roughly 19x outlier against every other model including its own sibling GPT-4o. Gemini's cheap tier handles the same photo as efficiently as GPT-4o's flagship, so this isn't "vision is expensive for cheap models" broadly. This specific tokenizer has a real gap, worth checking before assuming a price tier's text economics carry over to images.

### Forced tool-use removes the parsing problem, not the completeness problem
Every run across all 10 recipes and 3 providers' different function-calling implementations returned syntactically valid, schema-conformant JSON: no retries, no regex cleanup, no manual JSON repair. Turning unstructured text (or a photo of handwriting) into structured data used to be the hard part, and for this task, it no longer needs attention. What still needs attention, per several findings above, is whether the *content* inside that valid JSON is actually complete and correct: a different, harder problem that structured output alone doesn't solve.

## The eval tool

Local-only, never touches provider APIs (only reads what's already in `.cache/`), never deployed:

```bash
.venv/Scripts/python.exe eval/app.py
```

then open `http://127.0.0.1:5050`. Two-pane layout, recipe source on the left, rendered Gozinto on the right, each scrolling independently, click any cell to tag it from the fixed taxonomy, with the raw dependency data shown right in the popover. Every click writes immediately to `eval/scores/<run_id>.json`.

A companion judge tool exists (`eval/judge.py`, `eval/run_judge.py`, `eval/compare.py`) but is closed per the finding above, not part of the regular workflow.

## Stack

- Python, `anthropic`, `openai`, and `google-genai` SDKs: forced tool-use / function-calling extraction against a shared JSON schema, `temperature=0` (plus `seed` where supported) for as-deterministic-as-possible output (`src/providers/`)
- Flask + Jinja2: the local human-eval scoring tool (`eval/`)
- Plain server-rendered HTML/CSS (`src/gozinto_layout.py`, `src/gozinto_render.py`): dependency-depth ordering + `rowspan`-merged table, no client-side library at all
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

Full iteration-by-iteration history, every bug found, every prompt diff, every dead end, is in [ITERATION_LOG.md](ITERATION_LOG.md).

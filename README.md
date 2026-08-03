# Recipe Flowchart

Turns a recipe into a **Gozinto chart** (an industrial-engineering assembly diagram: ingredients converge through operations into a finished dish, read left to right) and tests how cheap a model can be while still getting that structure right.

Structuring unstructured text used to mean regex and endless if-chains. LLMs do it directly now, and the interesting question isn't whether they can, it's how little you have to spend to get a correct answer. This project runs the same recipe through six models across three providers, spanning a 25x per-token price range, and compares what each one actually produces, not just what it costs.

## What it does

1. **Input**: recipe text, a URL, or a photo of a recipe (including handwritten ones)
2. **Extraction**: one forced tool-use / function-calling request per model returns a title plus a flat list of nodes: `ingredient` nodes (name, amount, always a leaf) and `operation` nodes (a short technique label plus `inputs`, the ids of whatever it consumes — ingredients and/or earlier operations). `inputs` points backward at what feeds in, so the whole dependency graph falls out of one field per node, no separate step numbering
3. **Table generation**: the graph is layered (an operation's column is 1 + the deepest layer of its own inputs) and rendered as a plain server-side HTML `<table>`, `rowspan` merging every ingredient row that feeds a shared operation into one bracket-shaped cell
4. **Model comparison**: the same recipe runs against Claude Haiku 4.5, Claude Sonnet 5, GPT-4o mini, GPT-4o, Gemini 3.5 Flash-Lite, and Gemini 3.5 Flash, and the site shows cost, latency, and structure side by side

Since GitHub Pages can't run a live backend, the site is pre-generated: `src/build_site.py` runs the pipeline locally and bakes the results into a static `docs/index.html`. No API key ever reaches the browser.

## v1 &rarr; final

v1 (`29a0754`) rendered a flat list of steps as a Mermaid `graph TD` diagram, pasted into mermaid.live to preview. That didn't match how I actually plan a recipe by hand — a Gozinto/assembly chart with ingredients as rows converging through bracket-grouped technique labels — so the schema and renderer were both replaced: `depends_on` on a single flat step type became `inputs` on two node types (`ingredient`, `operation`), and Mermaid was dropped entirely for a self-contained, server-rendered HTML table with `rowspan` doing the bracket work CSS borders can't. No client-side library at all now, which is actually simpler than v1, not more complex. The provider layer and the 3 example recipes carried over unchanged; the model comparison grew from 4 models to 6 once Gemini got wired up (`src/providers/google_provider.py`) against the same forced-function-call pattern, via the `google-genai` SDK.

## The three examples

- **Cooked** (Serious Eats, Chinese Sweet and Sour Pork): marinate, dredge, fry the pork twice, fry the vegetables, and make the sauce are largely independent tracks that converge in one final toss, real parallel structure from a professionally edited recipe
- **Baked** (NYT Cooking, Spinach Egg Bites): mostly linear, but heating the oven, greasing the tin, and mixing the batter are genuinely independent until the fill step
- **Handwritten** (my own kitchen notes, Choux au Craquelin): a photo of bilingual Korean/English shorthand with hand-drawn brackets already marking which sub-steps run in parallel, chosen specifically to stress-test the vision-extraction path. No copyright concern since it's mine.

For the two web recipes, I pulled the text by hand rather than scraping: Serious Eats returns bot-protection responses to scripted requests, and NYT Cooking is gated in a way that blocks both direct fetches and browser automation. `src/scraper.py` still does the intended job (pulling ingredients and instructions from a site's `schema.org/Recipe` JSON-LD, verified working against AllRecipes) for any site that doesn't actively block it. Only the functional content, ingredients and instructions, is stored in this repo; editorial headnotes and photography stay on the original sites.

## Results

"Merges" is operations with 2+ inputs -- a proxy for whether the model actually caught convergence points, not just listed steps in order.

| Recipe | Model | Input tok | Output tok | Cost | Latency | Ingredients | Operations | Merges |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Cooked | Claude Haiku 4.5 | 2,608 | 2,114 | $0.0132 | 12.8s | 23 | 15 | 13 |
| Cooked | Claude Sonnet 5 | 3,174 | 2,403 | $0.0456 | 15.7s | 22 | 16 | 14 |
| Cooked | GPT-4o mini | 1,577 | 1,305 | $0.0010 | 12.2s | 24 | 9 | 6 |
| Cooked | GPT-4o | 1,577 | 1,587 | $0.0198 | 8.6s | 22 | 17 | 13 |
| Cooked | Gemini 3.5 Flash-Lite | 1,772 | 1,878 | $0.0052 | 4.7s | 21 | 15 | 13 |
| Cooked | Gemini 3.5 Flash | 1,772 | 2,001 | $0.0207 | 18.8s | 22 | 14 | 12 |
| Baked | Claude Haiku 4.5 | 1,975 | 1,100 | $0.0075 | 6.2s | 11 | 10 | 4 |
| Baked | Claude Sonnet 5 | 2,355 | 1,161 | $0.0245 | 8.1s | 11 | 9 | 4 |
| Baked | GPT-4o mini | 1,110 | 675 | $0.0006 | 6.3s | 11 | 8 | 1 |
| Baked | GPT-4o | 1,110 | 612 | $0.0089 | 3.6s | 10 | 7 | 2 |
| Baked | Gemini 3.5 Flash-Lite | 1,275 | 873 | $0.0026 | 2.6s | 10 | 8 | 4 |
| Baked | Gemini 3.5 Flash | 1,275 | 879 | $0.0098 | 42.2s | 10 | 8 | 4 |
| Handwritten | Claude Haiku 4.5 | 3,209 | 959 | $0.0080 | 5.9s | 10 | 9 | 5 |
| Handwritten | Claude Sonnet 5 | 3,894 | 1,237 | $0.0302 | 10.9s | 10 | 10 | 5 |
| Handwritten | GPT-4o mini | 37,690 | 529 | $0.0060 | 7.6s | 10 | 5 | 3 |
| Handwritten | GPT-4o | 1,960 | 609 | $0.0110 | 4.4s | 10 | 7 | 3 |
| Handwritten | Gemini 3.5 Flash-Lite | 2,092 | 758 | $0.0025 | 2.5s | 10 | 5 | 4 |
| Handwritten | Gemini 3.5 Flash | 2,092 | 908 | $0.0113 | 31.5s | 10 | 9 | 5 |

All 18 runs are `temperature=0` (plus a fixed `seed` on OpenAI and Gemini; Anthropic has no seed parameter) and cached to disk, so this is the actual pinned pass baked into `docs/index.html`, not a sample of a noisier distribution -- `temperature=0` narrows run-to-run variance but doesn't guarantee bit-identical output, so re-running with `--fresh` can still shift these slightly without changing the conclusions below.

## What I learned

### Price tier doesn't predict structural quality, in either direction -- or even consistently for the same model
On the cooked recipe, Gemini 3.5 Flash-Lite -- at $0.0052, roughly 1/9th Claude Sonnet 5's price -- found 15 operations and 13 merges, essentially matching Sonnet's 16 operations and 14 merges. GPT-4o mini, the single cheapest model in the lineup, found only 9 operations on that same recipe, the least granular breakdown of any model. But that pattern doesn't generalize: on the baked recipe the fewest-operations model is GPT-4o (7), not mini (8); on the handwritten recipe mini and Flash-Lite tie for fewest (5 each). Reading structural quality off the price tag doesn't work in either direction, and it doesn't even hold consistently for the same model across recipes -- there's no shortcut around actually checking the output.

### A "required" schema field isn't actually required
Every one of the 18 runs passed graph validation (no dangling `inputs`, no cycles) -- but Claude Sonnet 5 silently omitted the `title` field, marked `required` in the JSON schema, on all 3 real recipes, while every other model (Haiku, both GPT-4o tiers, both Gemini tiers) got it right on all 15 of their combined runs. This held even after moving to `temperature=0`, so it isn't sampling noise. The tell: Sonnet gets `title` correct on the four-node worked example in the prompt, and only drops it once the node list grows to teens or dozens of entries -- a field it clearly "knows" to fill, dropped under output-length pressure once forced tool-use has a big array to focus on. Schema-conformant isn't the same guarantee as schema-complete; the fix here (`build_site.py` falls back to any other run's title rather than trusting `PRIMARY_LABEL` blindly) is a reminder that "required" in a tool schema is a strong hint to the model, not an enforced constraint the way a database schema is.

### One outlier tokenizer, not a provider-wide pattern
On the handwritten photo, five of six models landed within a tight band -- GPT-4o (1,960), both Gemini tiers (2,092 each), Claude Haiku (3,209), Claude Sonnet (3,894) -- regardless of price tier. GPT-4o mini alone spiked to 37,690 input tokens, a 19x outlier against its own sibling model. That gap shrank mini's usual 15-30x cost edge on text recipes down to under 2x on this one photo ($0.0060 vs GPT-4o's $0.0110), but it didn't erase it. The lesson isn't "vision is expensive for cheap models" in general -- Gemini's cheap tier handled the same photo as efficiently as GPT-4o's flagship -- it's that *this specific* cheap tier has a real image-tokenizer gap worth checking before assuming a price tier's text-token economics carry over to images.

### The whole task still fits in pocket change (once, at least)
The single most expensive run (Sonnet 5 on the cooked recipe) cost $0.0456. All 18 runs together cost about 23 cents -- and after the first pass, they cost nothing at all: results are cached to disk keyed by provider, model, the recipe's own bytes, and the current prompt/schema/sampling settings, so `python src/build_site.py` re-renders instantly from cache and only `--fresh` (or an actual prompt/schema edit) triggers new paid calls.

### Forced tool-use removes the parsing problem, not the completeness problem
Every one of the 18 runs returned syntactically valid, schema-conformant JSON on the first try, across three different providers and three different function-calling implementations (Anthropic's forced tool-use, OpenAI's forced function-calling, Gemini's `FunctionCallingConfigMode.ANY`) -- no retries, no regex cleanup, no manual JSON repair. That's still the actual point of the project: turning unstructured text (or a photo of handwriting) into a structured dependency graph used to be the hard part, and it no longer needs attention. What still needs attention, per the finding above, is whether every field in that valid JSON is actually filled in.

### Not every documented API parameter works on every model
Passing `temperature=0` to Claude Sonnet 5 fails outright (`400: temperature is deprecated for this model`), while the same call works fine on Haiku 4.5 -- two models in the same family, same SDK call, different accepted parameters. `anthropic_provider.py` now tries with `temperature` first and falls back to a plain call on that specific error rather than hardcoding which models do or don't accept it, since that list is exactly the kind of thing that goes stale the next time a model ships.

## Stack

- Python, `anthropic`, `openai`, and `google-genai` SDKs: forced tool-use / function-calling extraction against a shared JSON schema, `temperature=0` (plus `seed` where the API supports it) for as-deterministic-as-possible output (`src/providers/`)
- Pillow: cropping the handwritten recipe photo
- `requests` + `schema.org/Recipe` JSON-LD parsing: URL scraping (`src/scraper.py`)
- Plain server-rendered HTML/CSS (`src/gozinto_layout.py`, `src/gozinto_render.py`): DAG layering + `rowspan`-merged table, no client-side library at all
- A content-addressed on-disk cache (`src/recipe_parser.py`, `.cache/`, gitignored): re-running the pipeline is free unless the recipe, prompt, schema, or sampling settings actually changed
- Jupyter: dev notebook mirroring the pipeline (`notebook.ipynb`)

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your own `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GOOGLE_API_KEY` (free tier available from [Google AI Studio](https://aistudio.google.com/apikey)).

Regenerate the site:

```bash
python src/build_site.py
```

Extraction results are cached to disk (`.cache/`), so re-running this is instant and free after the first pass. Pass `--fresh` to bypass the cache and force real API calls, e.g. after changing the prompt or schema:

```bash
python src/build_site.py --fresh
```

Or open `notebook.ipynb` to run the pipeline step by step.

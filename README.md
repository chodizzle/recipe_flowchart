# Recipe Flowchart

Turns a recipe into a flowchart showing which steps can happen in parallel and which have to wait on each other, then tests how cheap a model can be while still getting that structure right.

Structuring unstructured text used to mean regex and endless if-chains. LLMs do it directly now, and the interesting question isn't whether they can, it's how little you have to spend to get a correct answer. This project runs the same recipe through four models spanning a 15x price range and compares what each one actually produces, not just what it costs.

## What it does

1. **Input**: recipe text, a URL, or a photo of a recipe (including handwritten ones)
2. **Extraction**: one forced tool-use / function-calling request per model returns a structured step list, each step with an id, an imperative instruction, an estimated duration, and `depends_on`, the field that encodes the dependency graph
3. **Flowchart generation**: walks the `depends_on` graph and emits Mermaid syntax. Independent steps (empty `depends_on`) render as parallel branches that converge wherever a later step depends on both
4. **Model comparison**: the same recipe runs against Claude Haiku 4.5, Claude Sonnet 5, GPT-4o mini, and GPT-4o, and the site shows cost, latency, and structure side by side

Since GitHub Pages can't run a live backend, the site is pre-generated: `src/build_site.py` runs the pipeline locally and bakes the results into a static `docs/index.html`. No API key ever reaches the browser.

## The three examples

- **Cooked** (Serious Eats, Chinese Sweet and Sour Pork): marinate, dredge, fry the pork twice, fry the vegetables, and make the sauce are largely independent tracks that converge in one final toss, real parallel structure from a professionally edited recipe
- **Baked** (NYT Cooking, Spinach Egg Bites): mostly linear, but heating the oven, greasing the tin, and mixing the batter are genuinely independent until the fill step
- **Handwritten** (my own kitchen notes, Choux au Craquelin): a photo of bilingual Korean/English shorthand with hand-drawn brackets already marking which sub-steps run in parallel, chosen specifically to stress-test the vision-extraction path. No copyright concern since it's mine.

For the two web recipes, I pulled the text by hand rather than scraping: Serious Eats returns bot-protection responses to scripted requests, and NYT Cooking is gated in a way that blocks both direct fetches and browser automation. `src/scraper.py` still does the intended job (pulling ingredients and instructions from a site's `schema.org/Recipe` JSON-LD, verified working against AllRecipes) for any site that doesn't actively block it. Only the functional content, ingredients and instructions, is stored in this repo; editorial headnotes and photography stay on the original sites.

## Results

| Recipe | Model | Input tok | Output tok | Cost | Latency | Steps | Independent |
|---|---|---:|---:|---:|---:|---:|---:|
| Cooked | Claude Haiku 4.5 | 1,956 | 1,265 | $0.0083 | 5.8s | 17 | 5 |
| Cooked | Claude Sonnet 5 | 2,274 | 541 | $0.0149 | 5.2s | 9 | 2 |
| Cooked | GPT-4o mini | 1,011 | 554 | $0.0005 | 6.8s | 9 | 1 |
| Cooked | GPT-4o | 1,011 | 356 | $0.0061 | 3.0s | 10 | 2 |
| Baked | Claude Haiku 4.5 | 1,323 | 582 | $0.0042 | 2.8s | 9 | 2 |
| Baked | Claude Sonnet 5 | 1,455 | 472 | $0.0114 | 3.9s | 9 | 3 |
| Baked | GPT-4o mini | 544 | 246 | $0.0002 | 2.4s | 7 | 1 |
| Baked | GPT-4o | 544 | 265 | $0.0040 | 2.3s | 8 | 2 |
| Handwritten | Claude Haiku 4.5 | 2,557 | 549 | $0.0053 | 5.0s | 7 | 2 |
| Handwritten | Claude Sonnet 5 | 2,994 | 674 | $0.0191 | 6.0s | 12 | 2 |
| Handwritten | GPT-4o mini | 37,124 | 304 | $0.0058 | 4.4s | 9 | 2 |
| Handwritten | GPT-4o | 1,394 | 261 | $0.0061 | 3.1s | 6 | 2 |

All 12 runs are a single pinned pass, not an average. LLM output is stochastic, so re-running `build_site.py` will shift the exact numbers without changing the conclusions below.

## What I learned

### Cheaper doesn't mean structurally worse
On the cooked recipe, Haiku 4.5 (the cheapest Anthropic model here) found 5 independent steps and produced the most granular breakdown of any model, correctly flagging the dredge, the oil heating, and the sauce whisking as steps that don't have to wait on the pork. Sonnet 5, five times pricier per output token, collapsed almost the entire recipe into one strictly linear chain and found only 2 independent steps. The more expensive model captured *less* of the recipe's actual parallel structure in this run, which is the opposite of what the price tag would predict.

### Vision tokenization can erase a "light" model's cost advantage
GPT-4o mini used 37,124 input tokens on the handwritten photo, against GPT-4o's 1,394 for the same image. Mini's per-token rate is roughly 17x cheaper, but its image tokenizer is far less efficient, so the two models ended up costing almost the same on that one recipe ($0.0058 vs $0.0061). Text extraction is where the cheap model saves real money; image extraction is where that saving can quietly disappear.

### The whole task fits in pocket change
The single most expensive run (Sonnet 5 on the handwritten photo) cost $0.0191. Running all three recipes through all four models, twelve full extraction calls, cost about eight cents total. For a task like this, the deciding factor is reliability and structural accuracy, not budget: none of these models are expensive enough for cost alone to rule one out.

### Forced tool-use removes the parsing problem entirely
Every one of the 12 runs returned valid, schema-conformant JSON on the first try, across two different providers with two different function-calling implementations. No retries, no regex cleanup, no manual JSON repair. This is the actual point of the project: turning unstructured text (or a photo of handwriting) into a structured dependency graph used to be the hard part, and now it's the one part of the pipeline that doesn't need attention.

## Stack

- Python, `anthropic` and `openai` SDKs: forced tool-use / function-calling extraction against a shared JSON schema (`src/providers/`)
- Pillow: cropping the handwritten recipe photo
- `requests` + `schema.org/Recipe` JSON-LD parsing: URL scraping (`src/scraper.py`)
- Mermaid.js (via CDN, client-side): flowchart rendering, no server required
- Jupyter: dev notebook mirroring the pipeline (`notebook.ipynb`)

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your own `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (Google/Gemini is stubbed in `src/providers/google_provider.py`, not yet wired up: see the module docstring for what's needed).

Regenerate the site:

```bash
python src/build_site.py
```

Or open `notebook.ipynb` to run the pipeline step by step.

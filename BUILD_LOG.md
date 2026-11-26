# Build log: Agentic Commerce

**Last updated:** 2026-11-26 · **Branch:** `main` · **Tests:** 157 passing · **Notebooks:** all 11 run top to bottom offline

This file records how the project is built and how it runs, what every file is for, and what changed when. Read it before touching the code.

## Keeping this log current

After every change, before you commit:

1. Add an entry at the top of the [Change log](#change-log): the date, what changed, which files, why, and the test status.
2. If you added, removed, renamed or repurposed a file, update [Project structure](#project-structure) and [What each file does](#what-each-file-does).
3. If something started or stopped working, update [Current status](#current-status) and the header line above.

`tests/test_build_log.py` fails if a notebook, module, test, config or data file is missing from [What each file does](#what-each-file-does), so a new file can't be added without logging it. One-line decisions also go in `docs/decisions.md`.

## What the project is

A voice-to-voice multi-agent assistant for buying single Pokémon cards on Facebook Marketplace. It works out exactly which card each listing is, checks the price against TCGdex market data, flags likely scams, ranks the remaining listings for the buyer's persona, and answers in short natural speech. Four agents (Platform, Consumer, Merchant, Humanizer) share one LangGraph state graph. It is a course project run locally from VS Code: a terminal chat, a voice chat and a local web page that shows the agents at work (nothing is deployed). The plan is the "Project Plan v2" doc.

Pablo built the shared contracts (config, schemas, state, memory), the deterministic tools, the Consumer and Platform agents and the graph. Gaurav's side built the data pipeline, the Merchant and Humanizer agents and the shared LLM client, moved all code into notebooks, and fixed the bugs listed in the 2026-11-24 entry.

## Current status

**Works (offline, on sample data, tested):**

- The full graph: request parsing, at most one clarifying question (missing budget or several printings), search with one relaxed retry, risk scoring with flag explanations, policy rules, ranking, a number-checked spoken reply with template fallback, and memory between turns.
- Consultative price checks ("Is $45 fair for a base set Mewtwo?").
- The data pipeline end to end on the 28 synthetic raw listings, with fake Apify and TCGdex clients in the tests.
- Offline stand-ins for every LLM call, so everything runs with no keys (`AGENTIC_LLM=offline`).
- The voice chat's turn logic (filler timing, fallbacks, timing log) with fake speech services.
- The conversation: greeting and small talk, clarify, the "just to confirm" read-back and corrections.
- Live search on a replayed scrape: 100 listings per request, best of the fresh ones, progress lines.
- The 5-part listing score with spoken reasons, and the best 3 in the reply.
- The local web page (`--ui`): the chat, each graph step and live-search step as it happens, the search funnel and the ranked listings, typed or spoken into the page's microphone (replies read aloud), or following the voice chat.
- The evaluation set-up (notebook 08): the benchmark (100 listings, 50 queries, 5 memory scripts, answer key), the runner with 11 variants, the metrics, the judge, the statistics, the cost estimate and cap, and the pipeline and voice evaluations, all dry-run offline.

**Run for real (free-tier keys):**

- Gemini and Groq, on the 10 sample queries: 10/10 with both `gemini-3.8-flash` and `gpt-oss-20b`.
- The voice chat with Groq Whisper, Gemini agents and Edge-TTS, on Edge-TTS recordings of the sample requests, playback muted: 5/5 turns right (see the change log). Gaurav has also tried it with the microphone and speakers. The 5 timed runs for H5 are still to do.
- The new conversation and the live search path with Gemini, replaying the 100-listing scrape (no Apify charge): see the 2026-11-25 entry.
- The web page on the Mac with Groq agents and the replayed scrape, typed in the page: see the web page entry. Gaurav has used it and confirmed it works (2026-11-26).
- The page's microphone path on the Mac with real Groq Whisper and Edge-TTS, using recorded speech instead of a live microphone: see the microphone entry.
- The evaluation's free pilot on the Mac (2026-11-26): the full system on the 26 dev items with Groq's small model, the judge, speech to text in 4 voices, and the pipeline on the labeled samples; see the pilot entry.

**Not run for real yet:**

- A paid live search (100 listings, about $1.24 of Apify credit; $3.64 of this month's free credit is left).
- The first snapshot is scraped (100 listings) but not hand-checked, so without `--live` the agents still search the samples. The problems found in it are fixed in the pipeline; `data/listings.json` hasn't been rebuilt with the fixes yet.

**Not built yet:**

- Red-flag knowledge base grown from 10 to 30–40 entries with source links (tune it on the dev traps only).
- An answer key for queries on the real snapshot (the runner takes any pool and query file in the benchmark's format).

**Evaluation still to run:**

- The paid runs on the test split (3 repeats), estimated at about $6.60.
- The judge's check against 20 human ratings.
- The hand labels for the snapshot (pipeline accuracy on real data).
- Speech to text on real recorded voices.
- The 5 timed voice runs (H5).

**Known limits:**

- Sample prices are illustrative placeholders, not market data. Replies say so.
- Market prices are for ungraded single cards only. Graded cards, lots and non-English printings are out of scope.
- Gemini's replies run 235–375 characters, about 15–25 seconds of speech, and most repeat that the listings are samples. Fine on screen, long when spoken.
- TCGdex's Base Set Charizard holo price ($1,001.05) makes ordinary LP and MP Charizards at $400–450 look like 53–57% of market, so they are flagged as suspicious. Either that price or the condition multipliers (LP 0.85, MP 0.70) are too high for vintage cards; to settle in the hand check and threshold tuning.
- The Gemini free tier runs out after a day of testing; the agents then answer with the fixed template.
- Whisper still misspells some card names even with the vocabulary prompt ("Blast Toys", "Mewo"); the intent step has read every one correctly so far.

## How it runs

### Development workflow: notebooks are the source

```
notebooks/0X_*.ipynb  --(Export cell, or `uv run python -m src.nbexport`)-->  src/**/*.py
        ^ edit here                                                       generated, don't edit
```

- Code is written in notebook cells that start with `#| export`. A notebook names its default module once (`#| default_exp agents.merchant`); a cell starting `#| export tools.risk` goes to that module instead, so one notebook can hold several small modules.
- Exporting copies those cells, in order, into the modules (formatted with ruff). The import paths are the ones Pablo used (`from src.agents.consumer import ...`), so nothing else changed.
- The other notebooks pick up a change through `%autoreload`. The graph and the tests import the modules.
- `tests/test_notebooks.py` fails if a module is out of date with its notebook, and runs every notebook top to bottom offline.
- Hand-written Python: only `src/nbexport.py`, `src/__main__.py`, the `__init__.py` files, `eval/schema.py` and the tests.

### A conversation (`ChatSession`, notebook 07)

```
"Hi! I'm your AI card-shopping assistant. How are you doing today?"      greeting (AI disclosure)
buyer: "Pretty good!"          → one LLM line of small talk + "So what cards are we looking for today?"
                                 (if this reply already asks for a card, it goes straight on)
buyer: "a Base Set Charizard"  → the graph: INTENT → CLARIFY? (pause: "What's your budget?")
buyer: "under $400"            → INTENT → CONFIRM (pause): "Okay, so just to confirm: you're looking
                                 for a Charizard from Base Set, with a budget of $400.00. Is that right?"
buyer: "yes"                   → SEARCHING ... DONE: the best 3, each with why
       "no, make it $300"      → INTENT → CONFIRM once more; "no" alone → "What should I change?"
```

`dialogue.greet` and `dialogue.confirm` switch the greeting and the read-back; price checks never get a read-back. The graph only reads back when `ChatSession` asks for it (`confirm_first`), so the tests, the demo and the evaluation runner call it as before.

### One buyer turn (the graph in notebook 07)

```
START       a confirmed request (state `confirmed`) goes straight to SEARCHING; anything else to INTENT
INTENT      Consumer  LLM reads the request; memory fills budget/persona/condition it didn't state
  │ route_after_intent (Platform): card missing, budget missing, or several printings → CLARIFY;
  │                    else, if the conversation asked for a read-back → CONFIRM; else SEARCHING
CLARIFY     Platform  code decides, LLM words one question; the graph pauses for the answer
CONFIRM     Platform  the request read back in fixed wording; the graph pauses for yes or a correction
SEARCHING   Merchant  live search (with --live): scrape Marketplace for this card, identify, check and
  │                   price the fresh listings, and search only those. Then fuzzy match on name, set,
  │                   variant, min condition (relaxed on the retry)
EVALUATING  Merchant  risk = 1 − (1 − r_price)(1 − r_text)(1 − r_info); one LLM call explains
  │                   the flagged listings; price-check facts for consultative questions
  │ route_after_evaluating (Platform): nothing below the 0.6 gate → SEARCHING once, relaxed
RANKING     Consumer  landed cost → policy (budget, risk, reflection gate) → the 5-part listing score
  │                   (deal, condition, trust, convenience, confidence; 0–100) with reasons
RESPONDING  Humanizer facts with pre-formatted amounts and reasons → a short casual LLM reply
  │                   (the top pick with why, then two more) → number check
  │ route_after_responding (Platform): check failed → RESPONDING once more, then the template
DONE        Consumer  save profile and query to SQLite
```

`ChatSession` resends the original request with the clarify answer and any corrections. Without the greeting, it puts the AI disclosure on the first reply of the session.

### Where listings come from

- **Samples** (default, `data.use_samples: true`): `data/samples/sample_listings.json` and `sample_prices.json`.
- **Snapshot**: notebook 02 scrapes Marketplace (Apify: the 10 searches in `scrape.queries`, one run each, `scrape.per_query` listings per search), anonymizes, drops the obvious out-of-scope listings by title, identifies cards (20 per LLM call, 4 calls at a time, reusing cards identified before), filters the scope, settles each card's set and fetches its price on TCGdex, and writes `data/listings.json`, `data/prices.json` and `data/listings_review.csv` for the hand check. Then set `data.use_samples: false`.
- **Live search** (`--live`, or `merchant.live: true`): each confirmed request scrapes `merchant.live_limit` (100) Marketplace listings for that card, about $1.24 of Apify credit, and the reply picks only from those fresh listings. The same pipeline steps run on them, plus a pre-filter that drops listings that never name the card. They are also appended to `data/live_listings.json`. Live mode uses the real data and TCGdex prices, never the samples.
- **Replay** (`--replay FILE`, or `merchant.live_replay`): the live path on a saved scrape from `data/raw/`, for free and the same every time.

### The web page (`--ui`, notebook 10)

```
python -m src --ui            type or talk in the page   python -m src --voice --ui   talk; the page follows
        │                                                        │
 BrowserChat ── ChatSession.send(text, on_task=board.on_task) ── VoiceChat (board=...)
        │                    │                    │
        └──────────── LiveBoard: numbered events ─┘   info · chat · note · turn · task · progress · results · error
                             │
     http.server on 127.0.0.1:8765   /  the page (src/web/index.html)
                                     /api/events  server-sent events; a reconnect resumes after its last event
                                     /api/send    a typed message (refused in voice mode)
                                     /api/voice   a recording from the page's microphone
                                     /api/speech  the MP3 of one line (Edge-TTS), for reading aloud
```

The page's microphone: click, talk, click again (Esc cancels). The browser records (WebM in Chrome, MP4 in Safari) and checks the recording isn't too short or silent; the server transcribes it with the voice chat's `Transcriber` (Groq Whisper with the card-name vocabulary, then Gemini) and runs the turn. For a spoken turn, the page reads aloud the casual lines during the search (a `Narrator` sends them as notes: the search line, a line per step, a still-working line, the filler) and the reply, sentence by sentence, in the voice chat's voice; the browser's own voice reads a line if Edge-TTS fails. Typed turns stay silent. "Read aloud" (top of the chat) switches it off; "Stop", or clicking the microphone again, cuts it short.

```
┌ header: what the listings are (live, replay, samples), the model, connected ┐
│ Conversation        │ What the agents are doing: each graph step with a timer,  │
│ every line, typed   │   the live search's steps, the parsed request             │
│ or spoken; lines    │ Search results: how the search narrowed down (funnel),    │
│ said while the      │   the top pick (card picture, total on a price sticker,   │
│ search runs;        │   condition, rarity, market value for its condition and   │
│ "Yes, search" at    │   its source and date, seller's city, distance, listing   │
│ the read-back       │   date, score and reasons), the two alternatives, all     │
│ [type here]         │   ranked listings (sort, filter, click for details), and  │
│                     │   the ones that didn't make the cut                       │
└─────────────────────┴────────────────────────────────────────────────────────────┘
```

The page is dark: navy panels on a darker base, the green "felt" for progress and good deals, and the yellow price sticker. Each search gets a tab. Reloading the page replays the whole conversation. Card pictures load from TCGdex's image server; everything else comes from the local server.

What the page can't show: **seller names**. Our Marketplace scraper doesn't return them (Facebook hides them from logged-out scrapers; the actors that get them need Facebook login cookies), so the page shows the seller's city, distance, listing date and signals and links to the listing, where the name is one click away. The links exist only for live and replayed searches, and only in the running system's memory.

### Evaluation (notebook 08)

```
eval/data/ (benchmark, frozen)      python -m src.evaluation run --variants ... --split dev|test --repeats N
  pool.json       100 listings  ─┐            │ each variant × query × repeat: ChatSession (four agents) or
  prices.json     fixed prices   ├──────────▶ │ one LLM call (single agent), clarify answered from the script
  queries.json    50 + key      ─┤            ▼
  memory_scripts  5 × 2 turns   ─┘   eval/results/<time>_<label>/results.csv, replies.jsonl, run.json
                                              │ judge → naturalness_score   stats → summary.csv, comparisons.csv,
                                              ▼ by_category.csv, report.md   estimate → cost of a full run
```

- **The benchmark** (`src/benchmark.py`): 10 real printings, each with 4 clean listings, 3 traps (scams) and 3 decoys (honest but odd). Dev traps use the red-flag knowledge base's wording; test traps use new wording, so the test split measures generalization. 50 queries (15 simple, 25 complex, 10 consultative) and 5 two-turn memory scripts, each with its ground truth. The answer key comes from an oracle that only sees the ground truth (right card, condition, budget, not a trap) and scores value, condition and visible safety with its own weights per buyer type; acceptable picks are within 0.08 of the best.
- **Variants** (`evaluation.variants`): `full`, `single_agent` (one call with every listing and the same tool outputs), `frontier_single` (plan ablation 6), `small_model` (5), `no_reflection` (3), `no_rag`, `no_clarify`, `no_number_check`, `template_reply`, `no_memory`, `plan_scoring`.
- **Metrics** (eval/schema.py's columns plus a few): top-1/top-3 accuracy, correct refusals, policy violations, traps recommended, scam recall (bait traps kept out of the spoken picks), false positives (passing over an honest decoy that was the only right answer), arithmetic errors (an amount no listing, price or budget has), memory turns right without asking again, naturalness (judge), latency (real calls only), tokens, cost.
- **Statistics**: per query (averaged over repeats), 95% bootstrap intervals, each variant against `full` on the same queries (paired change, exact McNemar test), and results by query type.
- **Scam screening** (`screen`): the Merchant's check on every benchmark listing, by split. Offline already: dev traps 100% caught, test traps 21% (new wording), honest decoys rejected 7% (dev) and 20% (test: "custom sleeve", "unofficial sleeve").
- **Pipeline** (`src/eval_pipeline.py`): the scrape's health without labels; with hand labels, scope precision/recall, each identity field's accuracy, price coverage, time and cost per listing.
- **Voice** (`src/eval_voice.py`): word error rate and entity recall of Whisper on the requests spoken by 4 Edge-TTS voices (US, UK, Indian English), with and without the vocabulary prompt; spoken vs typed top picks; H5 from the voice chat's timing log; Edge-TTS time to the first sentence.
- **Cost**: tokens are logged per call and priced from `evaluation.prices_per_million`; `--max-cost` stops a run at a cap; the model never falls back to another one during a run.

### Switches

| Where | Switch | Effect |
|---|---|---|
| each notebook's setup cell | `LIVE` | `True` = Gemini with your keys; `False` = offline stand-ins |
| notebook 02 | `SCRAPE`, `TEST_RUN` | run Apify (costs credit); 1 listing per search (10) instead of 10 per search (100) |
| environment | `AGENTIC_LLM=offline` (or `primary`, `small`, ...) | overrides `llm.active` for everything; the tests set `offline` |
| environment | `NB_NO_EXPORT=1` | running a notebook doesn't rewrite `src/` (the tests set it) |
| `config.yaml` | `llm.active`, `llm.fallback` | model for all agents; model used when the quota runs out |
| `config.yaml` | `data.use_samples` | samples vs the real snapshot |
| `config.yaml` / command line | `merchant.live` / `--live` | live Marketplace search per confirmed request (costs Apify credit) |
| `config.yaml` / command line | `merchant.live_replay` / `--replay FILE` | the live path on a saved scrape (free) |
| `config.yaml` | `dialogue.greet`, `dialogue.confirm` | the greeting and small talk; the "just to confirm" read-back |
| `config.yaml` | `scoring.method` | `five_part` (default) or `plan` (Plan v2's U = w1·P + w2·C + w3·T) |
| `config.yaml` | `ingest.parallel_calls`, `ingest.prefilter`, `ingest.identified_cache`, `ingest.llm` | identification speed: calls at a time, the title pre-filter, reuse of cards identified before, the model for identification |
| `config.yaml` | `rag.enabled` | Chroma retrieval for flag explanations (keywords always run) |
| `config.yaml` | `evaluation.variants`, `evaluation.prices_per_million`, `evaluation.voices` | the ablation variants, model prices for the cost numbers, the voices that speak the test requests |
| command line | `--ui`, `--port`, `--no-browser`, `--no-mic` | the local web page, its port, whether a browser tab opens, no microphone button |
| `config.yaml` | `ui.port`, `ui.open_browser`, `ui.max_rows`, `ui.card_cache` | the web page's port (the next free one if taken), the browser tab, listings shown per search, where card details are kept |

### Running it in VS Code

- **Run and Debug panel** (play icon with a bug in the sidebar, or Cmd+Shift+D): pick a configuration and press the green arrow. "Demo: run sample queries (offline)" prints PASS/FAIL for the 10 sample queries; "Text chat (offline)" / "Text chat (Gemini)" chat in the terminal; "Voice chat (Gemini)" talks (press Enter, speak, press Enter); "Web page (Gemini)" and "Voice chat + web page (Gemini)" open the local web page (add them to `launch.json` from the 2026-11-25 web page entry if they aren't there yet). On a Mac, VS Code needs microphone permission first: System Settings → Privacy & Security → Microphone.
- **Testing panel** (flask icon): Run All Tests.
- **Notebooks**: open one, pick the `.venv` (Python 3.14) kernel, Run All.

### Commands

```bash
uv run python -m src --demo --offline   # the 10 sample queries, PASS/FAIL each
uv run python -m src --offline          # chat in the terminal (drop --offline to use Gemini)
uv run python -m src --voice           # voice chat (--keyboard to type, --mute to print, --audio FILE)
uv run python -m src --voice --replay data/raw/snapshot_20261125_154037.json   # live path, free
uv run python -m src --voice --live    # live Marketplace search per request (about $1.24 each)
uv run python -m src --ui --offline    # the web page with a typed chat (drop --offline for Gemini)
uv run python -m src --ui --replay data/raw/snapshot_20261125_154037.json   # page + live path, free
uv run python -m src --voice --ui --replay data/raw/snapshot_20261125_154037.json   # talk, watch the page
uv run python -m src.evaluation run --variants all --split dev --model offline   # evaluation wiring, free
uv run python -m src.evaluation run --variants full,single_agent --split dev --model small --label pilot
uv run python -m src.evaluation estimate eval/results/<pilot folder> --repeats 3   # cost of the full run
uv run python -m src.evaluation run --variants all --split test --repeats 3 --max-cost 25 --label final
uv run python -m src.evaluation judge eval/results/<folder>   # then stats, rating-sheet, agreement
uv run python -m src.eval_pipeline score data/samples/sample_raw_listings.json eval/data/sample_raw_labels.csv
uv run python -m src.eval_voice stt --split dev --limit 10   # Edge-TTS voices -> Groq Whisper
uv sync                              # Python 3.14 + everything (incl. ipykernel and nbmake)
uv run pytest                        # all tests offline, incl. running every notebook
uv run python -m src.nbexport        # export all notebooks to src/
uv run python -m src.nbexport --check   # exit 1 if a module is stale
uv run ruff check . && uv run ruff format --check .   # what CI runs, notebooks included
```

## Project structure

Every file in the repo (files that exist only on your machine are listed further down):

```
Agentic-Commerce/
├── README.md                        # GitHub front page: what it is, setup, how to run
├── BUILD_LOG.md                     # this file
├── config.yaml                      # every model id, threshold, weight and path
├── pyproject.toml                   # Python 3.14, dependencies, pytest and ruff settings
├── uv.lock                          # exact package versions (uv writes it)
├── .python-version                  # 3.14, read by uv
├── .env.example                     # names of the API keys
├── .gitignore                       # what git never commits
├── .pre-commit-config.yaml          # optional git hooks
├── .github/workflows/ci.yml         # GitHub Actions: ruff + pytest on every PR
├── .vscode/
│   ├── settings.json                # .venv interpreter, pytest, ruff on save
│   └── launch.json                  # Run and Debug entries (demo, chat, voice chat, tests)
├── notebooks/                       # THE SOURCE CODE, one notebook per agent
│   ├── 00_foundation.ipynb          # → src/config.py, schemas.py, state.py, memory.py, llm.py
│   ├── 01_tools.ipynb               # → src/tools/landed_cost.py, utility.py, policy.py, prices.py, risk.py
│   ├── 02_data_pipeline.ipynb       # → src/pipeline.py
│   ├── 03_consumer_agent.ipynb      # → src/agents/consumer.py
│   ├── 04_merchant_agent.ipynb      # → src/agents/merchant.py
│   ├── 05_humanizer_agent.ipynb     # → src/agents/humanizer.py
│   ├── 06_platform_agent.ipynb      # → src/agents/platform.py
│   ├── 07_orchestration.ipynb       # → src/graph.py
│   ├── 08_evaluation.ipynb          # → src/benchmark.py, evaluation.py, eval_pipeline.py, eval_voice.py
│   ├── 09_voice.ipynb               # → src/voice.py
│   └── 10_interface.ipynb           # → src/ui.py
├── src/                             # generated from the notebooks, except where noted
│   ├── __init__.py                  # hand-written package marker
│   ├── __main__.py                  # hand-written: `python -m src`
│   ├── nbexport.py                  # hand-written: notebooks → src/
│   ├── config.py  schemas.py  state.py  memory.py  llm.py
│   ├── pipeline.py
│   ├── graph.py
│   ├── voice.py
│   ├── ui.py
│   ├── benchmark.py  evaluation.py  eval_pipeline.py  eval_voice.py
│   ├── web/index.html               # hand-written: the web page
│   ├── agents/
│   │   ├── __init__.py              # hand-written package marker
│   │   └── consumer.py  merchant.py  humanizer.py  platform.py
│   └── tools/
│       ├── __init__.py              # hand-written: re-exports Pablo's tools
│       └── landed_cost.py  utility.py  policy.py  prices.py  risk.py
├── data/
│   ├── red_flags.md                 # scam red-flag knowledge base
│   ├── raw/.gitkeep                 # keeps data/raw/ in git; scrapes saved there are not committed
│   └── samples/
│       ├── sample_listings.json     # 24 synthetic listings (the pool until real data exists)
│       ├── sample_prices.json       # illustrative prices for the 8 sample printings
│       ├── sample_raw_listings.json # 28 Apify-shaped raw items for the pipeline dry run
│       └── sample_queries.json      # 10 test requests with expected answers
├── docs/decisions.md                # one line per decision, with the reason
├── eval/
│   ├── schema.py                    # columns of results.csv for the evaluation runs
│   └── data/                        # the benchmark (frozen) and the sample labels
│       ├── pool.json  prices.json  queries.json  memory_scripts.json
│       └── sample_raw_labels.csv    # hand labels for the 28 sample raw listings
└── tests/                           # 19 test files + conftest.py, all offline (157 tests)
```

## What each file does

"Edit?" says how a file is meant to change: **yes** (edit it directly), **notebook** (generated: edit the notebook named, then run its Export cell), **tool** (a program writes it), or **rarely**.

### Notebooks: the source code

Each notebook holds the code for its modules in `#| export` cells, explains it in markdown, and ends with a "Try it" section that runs it on the sample data and an Export cell. Every notebook starts with `LIVE = False` (offline, free); set `LIVE = True` to use Gemini.

| File | Purpose | Edit? |
|---|---|---|
| `notebooks/00_foundation.ipynb` | The shared base every agent imports: the config loader and repo paths, the data types (listing, query, evaluated listing), the graph state, the SQLite buyer memory, and the one LLM client all agents share (Gemini or Groq, response cache, retry on rate limits, switch to the free-tier model when the quota runs out, offline stand-ins). | yes |
| `notebooks/01_tools.ipynb` | The plain-Python rules, no LLM: landed cost (price + shipping + tax), the listing score (deal against the market price, condition, trust, convenience and identification confidence, weighted per buyer type into 0–100, with spoken reasons; Plan v2's formula kept as an option), the policy rules (budget cap, scam gate, reflection before ranking, number check before speech), market-price lookups and the scam risk score. | yes |
| `notebooks/02_data_pipeline.ipynb` | Builds the listing data: scrape Facebook Marketplace through Apify, strip seller details (keeping photo count, posting date, pickup distance, public meetup, pending), drop $0 and $1 placeholder prices, identify each card with the LLM, drop graded cards, lots and non-English cards, settle each card's set with TCGdex (printed set size, name check, aliases, promo numbers), fetch market prices, write `data/listings.json` and the review sheet. Also `ReplayScraper` (a saved scrape instead of Apify). Without `SCRAPE = True` it does a dry run on the samples into a temp folder. | yes |
| `notebooks/03_consumer_agent.ipynb` | Consumer Agent (Pablo's): reads the buyer's request (INTENT), fills gaps from memory, ranks the safe listings (RANKING), saves the profile (DONE). | yes |
| `notebooks/04_merchant_agent.ipynb` | Merchant Agent: finds matching listings (SEARCHING), scores each one's scam risk and explains the risky ones in a sentence (EVALUATING), answers price checks. With live search on, each request scrapes Marketplace (100 listings), picks only from those fresh listings and reports its progress. | yes |
| `notebooks/05_humanizer_agent.ipynb` | Humanizer Agent (RESPONDING): turns the result into a short spoken reply (the top pick with why, then two more with their main reason), checks every dollar amount and card name against the data, retries once, then falls back to a fixed template. | yes |
| `notebooks/06_platform_agent.ipynb` | Platform Agent (Pablo's, extended): decides when to ask a clarifying question and asks it (CLARIFY), reads the request back before searching (CONFIRM) and reads the buyer's answer, the small-talk line, and the routers for the bounded loops. | yes |
| `notebooks/07_orchestration.ipynb` | Wires the four agents into the LangGraph state graph, runs conversations (`ChatSession`: greeting, small talk, the request, clarify, read-back, search), and holds the terminal chat (`--live`, `--replay`) and demo. Runs all 10 sample queries and has a chat loop. | yes |
| `notebooks/08_evaluation.ipynb` | The evaluation: the benchmark (100 synthetic listings with traps and decoys, fixed prices, 50 queries and 5 memory scripts, the answer-key oracle), the ablation runner (11 variants including a single-agent baseline), the metrics, the LLM judge and its check against human ratings, the statistics, the cost estimate and cap, the scam screening, and the scraping-pipeline and voice evaluations. Its demo runs offline. | yes |
| `notebooks/09_voice.ipynb` | The voice chat around the same `ChatSession`: the spoken greeting, push-to-talk recording, Groq Whisper speech to text (Gemini as fallback), casual lines while a live search runs ("Hold up a sec while I swim the internet for you!", progress and "still swimming" lines), a filler when EVALUATING starts, Edge-TTS replies sentence by sentence (macOS `say` as fallback) and the timing log. Its demo runs offline with stand-ins; `SPEECH = True` uses the real services. With `--ui` the web page follows the conversation. (08 is kept for the evaluation runner.) | yes |
| `notebooks/10_interface.ipynb` | The local web page: `LiveBoard` (everything that happens in a conversation as numbered events), the listing rows the page shows (price and total, condition, rarity, market value for the condition with its source, date and TCGplayer link, the seller's city, distance, listing date and signals, the score with its parts and reasons, red flags, the listing link), card details from TCGdex (`CardDetails`), the search funnel, the web server (server-sent events) and `BrowserChat` (typed messages from the page). The microphone: `PageVoice` (transcribes the page's recordings, makes the MP3 of each line read aloud) and `Narrator` (the lines said during a spoken turn's search). Its demo runs one conversation offline and can start the server. | yes |

### Python package (`src/`)

These are what the graph, the tests and the other notebooks import. All but four are generated from the notebooks.

| File | Purpose | Edit? |
|---|---|---|
| `src/__init__.py` | Empty marker that makes `src` an importable package. | rarely |
| `src/__main__.py` | A few lines: `python -m src` starts the terminal chat (`--offline`, `--demo`), `python -m src --voice` the voice chat, `python -m src --ui` the web page (with `--voice`, the voice chat with the page). The Run and Debug entries use it. | rarely |
| `src/nbexport.py` | The export tool: copies `#| export` cells into the modules below and formats them; `--check` reports modules that are out of date with their notebook. | rarely |
| `src/config.py` | Finds the repo root, loads `config.yaml`, turns config paths into absolute paths, reads API keys from `.env`. | notebook 00 |
| `src/schemas.py` | The data types shared by all agents: `CardListing` (one anonymized listing and its identified card), `ParsedQuery` (what the buyer asked for), `LandedCostResult`, `EvaluatedListing` (a listing plus market price, risk, warning, cost and score). | notebook 00 |
| `src/state.py` | `AgentState`: the typed dictionary LangGraph passes between nodes; each agent reads and writes its own fields. | notebook 00 |
| `src/memory.py` | `BuyerMemory`: saves each buyer's budget, persona and preferences, and a history of their requests, in SQLite. | notebook 00 |
| `src/llm.py` | The shared LLM client (`make_llm`): model choice from config or `AGENTIC_LLM`, structured JSON output, disk cache, retries, quota fallback, token counts, and the offline mode. | notebook 00 |
| `src/pipeline.py` | Scraper (`MarketplaceScraper`, `ReplayScraper`), anonymizer, title pre-filter (`prefilter`), card identification (`extract_cards`: parallel batches, `IdentifiedCache`; `identify_listings` runs pre-filter → identification → scope filter), TCGdex client and price cache (`PriceBook`: set resolution, `verify_cards`), review sheet, `run_ingest`, and `load_data`, which gives the Merchant its listing pool (samples or the real snapshot). | notebook 02 |
| `src/graph.py` | `build_graph()` (the LangGraph wiring, with CONFIRM and a start router for confirmed requests), `ChatSession` (greeting, small talk, clarify, read-back and corrections, AI disclosure; `send(text, on_task=...)` reports each node and each live-search step, with its details), `run_sample_queries()`, `live_mode()` and `main()` (terminal chat and demo). | notebook 07 |
| `src/benchmark.py` | The benchmark: printings, the 100 listing specs, the 50 query specs and 5 memory scripts, the oracle (`answer_key`), `build_benchmark()` (writes eval/data) and `load_benchmark()`. | notebook 08 |
| `src/evaluation.py` | The runner: `Variant`, `MultiAgent` and `SingleAgent`, `score()` (the metrics), `run()` (results.csv, replies.jsonl, cost cap), `judge()`, `rating_sheet()`, `judge_agreement()`, `summarize()` (bootstrap intervals, McNemar, report.md), `screening()`, `estimate()`, `main()` (`python -m src.evaluation`). | notebook 08 |
| `src/eval_pipeline.py` | The scraping pipeline's evaluation: `scrape_health()`, `label_sheet()` (the hand-check sheet), `score_pipeline()`, `main()` (`python -m src.eval_pipeline`). | notebook 08 |
| `src/eval_voice.py` | The voice evaluation: `wer()`, `entity_recall()`, `run_stt()` (Edge-TTS voices → Whisper, with and without the vocabulary; voice-to-voice picks), `timing_summary()` (H5), `tts_latency()`, `main()` (`python -m src.eval_voice`). | notebook 08 |
| `src/voice.py` | `PushToTalk` (recording), `Transcriber` (Groq Whisper, Gemini fallback), `Voice` (Edge-TTS with a 3-second silence limit, local voice fallback, clip cache; `mp3()` gives the raw audio, which the web page uses), `Speaker` (playback, `busy`), `speakable()`, `sentences()`, `VoiceChat` (the greeting; one spoken turn: live-search lines, still-working thread, filler, reply, timing row), `main()` (`python -m src --voice`, `--ui` for the web page) and `synthesize_requests()` (test recordings). | notebook 09 |
| `src/ui.py` | The web page's Python side: `LiveBoard`, `listing_row()` and `results()` (what the page shows per listing and per search), `funnel()`, `CardDetails` (rarity, picture and TCGplayer product id from TCGdex, cached), `serve()` (the local web server: the page, events, typed messages, recordings, speech), `PageVoice` and `Narrator` (the microphone and reading aloud), `BrowserChat` (typed and spoken turns), `open_page()` and `main()` (`python -m src --ui`). | notebook 10 |
| `src/web/index.html` | The web page itself: plain HTML, CSS and JavaScript, no build step. Listens to `/api/events`, sends typed messages to `/api/send` and recordings from its microphone button to `/api/voice`, and reads spoken turns aloud with `/api/speech`. | yes (hand-written) |
| `src/agents/__init__.py` | Package marker for the agents. | rarely |
| `src/agents/consumer.py` | INTENT, RANKING and DONE nodes; `apply_memory()` fills only what the buyer didn't say. | notebook 03 |
| `src/agents/merchant.py` | SEARCHING and EVALUATING nodes; search filters, the printing list used by CLARIFY, red-flag retrieval with Chroma, flag explanations, price check, live search (`live_refresh`, `progress`; the summary keeps each fresh listing's link in memory for the web page). | notebook 04 |
| `src/agents/humanizer.py` | RESPONDING node; reply facts (with each pick's reasons; the sample-data note once per conversation), the casual reply prompt, the number check, the template reply. | notebook 05 |
| `src/agents/platform.py` | CLARIFY and CONFIRM nodes, the rule for when to ask, the read-back wording (`describe_request`), reading the answer (`read_confirmation`), small talk, and the routers. | notebook 06 |
| `src/tools/__init__.py` | Re-exports Pablo's tools so `from src.tools import compute_landed_cost` works. | rarely |
| `src/tools/landed_cost.py` | Total cost: price + shipping + tax; $0 shipping for pickup, a $5 estimate (flagged) when shipping is unknown. | notebook 01 |
| `src/tools/utility.py` | The listing score (`score_listing`: five parts, persona weights from `scoring`, reasons) and the ranking; Plan v2's U = w1·price + w2·condition + w3·trust as `scoring.method: plan`. | notebook 01 |
| `src/tools/policy.py` | The hard rules: over-budget and risky listings rejected, the closest rejected one kept for "nothing fits" replies, and guards that stop ranking before reflection or speech before the number check. | notebook 01 |
| `src/tools/prices.py` | Market price for a listing's exact printing and variant, adjusted for condition; finds a card's price entry for price checks. | notebook 01 |
| `src/tools/risk.py` | Reads `data/red_flags.md`, matches red-flag phrases (ignores "not a proxy"), and computes the risk score and reject/warn/ok decision. | notebook 01 |

### Data

| File | Purpose | Edit? |
|---|---|---|
| `data/red_flags.md` | The scam knowledge base: 10 entries, each with severity, the phrases that trigger it, why it matters and a source. Used for the risk score and the flag explanations. Planned: 30–40 entries with sources. | yes |
| `data/raw/.gitkeep` | Empty file that keeps the `data/raw/` folder in git. Raw scrapes saved there are never committed (they contain listing links and sellers' locations). | no |
| `data/samples/sample_listings.json` | 24 synthetic listings already in the `CardListing` format: 11 clean, 7 traps (scams), 6 decoys (honest but odd), all in the dev split. The agents search these until `data/listings.json` exists and `data.use_samples` is false. | yes |
| `data/samples/sample_prices.json` | Illustrative market prices for the 8 sample printings, keyed like `base1-4`, in the same format as `data/prices.json`. Not real market data. | yes |
| `data/samples/sample_raw_listings.json` | 28 items shaped like Apify's Marketplace output (incl. graded, lots, a Japanese card) for the pipeline dry run in notebook 02 and the pipeline tests. | yes |
| `eval/data/pool.json` | The benchmark's 100 listings (`CardListing` format, with label, split and why each trap or decoy is one), dated relative to 2026-11-25. Built by notebook 08; frozen. | tool (`build`) |
| `eval/data/prices.json` | The benchmark's fixed market prices for its 10 printings. | tool (`build`) |
| `eval/data/queries.json` | The 50 queries: text, category, split, ground truth, scripted clarify answer, and the answer key (expected outcome, acceptable picks, bait traps, oracle scores). | tool (`build`) |
| `eval/data/memory_scripts.json` | The 5 two-turn conversations for memory, with each turn's answer key. | tool (`build`) |
| `eval/data/sample_raw_labels.csv` | Hand labels (in scope or why not; card, set, number, variant, condition) for the 28 sample raw listings, for the pipeline evaluation. | yes |
| `data/samples/sample_queries.json` | 10 buyer requests with the expected outcome (recommend, nothing fits, price check), acceptable top picks and a scripted clarify answer. Used by the tests, notebook 07 and the demo. | yes |

### Tests (`tests/`, all offline: no keys, no network)

| File | Purpose |
|---|---|
| `tests/__init__.py` | Package marker. |
| `tests/conftest.py` | Sets offline mode for every test and provides shared fixtures: config, sample data, LLM, a temporary memory database, the sample queries. |
| `tests/test_landed_cost.py` | Pablo's: shipping rules, the $5 estimate, tax. |
| `tests/test_utility.py` | Pablo's: the utility formula and persona ranking. |
| `tests/test_scoring.py` | The 5-part score: deal against the market price, reasons (and none for a suspicious price), trust signals, pickup distance, buyer-type weights, the plan formula option. |
| `tests/test_policy.py` | Pablo's: budget and risk rejections, the closest rejected listing, the order guards. |
| `tests/test_memory.py` | Pablo's: saving and updating a profile, query history. |
| `tests/test_orchestrator_consumer.py` | Pablo's: the routers and an end-to-end graph run with fake agents. |
| `tests/test_platform_consumer_fixes.py` | Regression tests for the bugs fixed in review: stated persona vs saved persona, the printing question. |
| `tests/test_pipeline_offline.py` | Anonymizing (listing signals, placeholder prices), the title pre-filter, card identification in parallel batches and the identified-card cache, `identify_listings`, scope filter, set-name lookup and aliases, printed set size, TCGdex card verification, promo numbers, the review sheet, the Apify input and response, a full `run_ingest` with fake Apify and TCGdex. |
| `tests/test_merchant.py` | Search filters, red-flag matching, risk on traps and decoys, the two nodes, ablation 3 (no reflection), price check. |
| `tests/test_humanizer.py` | The number check, the retry with the error, the template fallback (the casual wording, reasons not repeated, each alternative's warning), the "over budget by" wording. |
| `tests/test_graph_offline.py` | The whole graph: all 10 sample queries, the clarify turn, memory across turns, price check, the AI disclosure, `python -m src`. |
| `tests/test_dialogue.py` | The conversation: greeting and small talk, a reply to the greeting that is already a request, the read-back, corrections and their limit, clarify then read-back, price checks without one, the read-back wording, reading yes, no and corrections, the sample-data note said once. |
| `tests/test_live_search.py` | Live search with a replayed scrape and fake TCGdex: picks only fresh listings at TCGdex prices, progress events in order, no second scrape for the same search, never the sample prices. |
| `tests/test_voice.py` | The voice chat with fake speech services: WAV format, speech wording, the Whisper → Gemini fallback, the Edge-TTS fallback, silence limit and clip cache, the filler starting with EVALUATING and none on a clarifying question, the live-search, progress and still-working lines, the spoken greeting, silent recordings, streamed turns matching plain ones, `python -m src --voice`. |
| `tests/test_ui.py` | The web page offline: the events of a conversation, each listing's market value, source and seller side, links and the funnel on a live search, card details fetched once and never offline, "nothing fits", one typed message at a time, a failed turn, the web server (page, events with resume, chat, voice mode refusing typing), the voice chat mirrored to the page, `python -m src --ui`; the microphone: a recording transcribed, narrated and its reply read aloud, what it refuses (off, too short, a failed transcription), each line in the voice chat's voice with fixed lines cached, the warm-up, the search lines of a spoken live search. |
| `tests/test_evaluation.py` | The evaluation offline: the committed benchmark matches the code, the pool's balance and neutral ids, dates moving with today, the query mix, an answer key that never accepts a trap, the collector oracle, price-check keys, each metric, every variant running and writing the schema, memory scripts with and without memory, the cost cap, the single agent's one call, the judge with the rating sheet and agreement, the cost estimate, the scam screening, the pipeline evaluation and label sheet, the word error rate, speech to text with fake services, H5 timing, TTS latency, `python -m src.evaluation`. |
| `tests/test_llm.py` | Model routing, the quota fallback, and that every schema sent to Gemini is one Gemini accepts. |
| `tests/test_notebooks.py` | Every module matches its notebook, and every notebook runs top to bottom. |
| `tests/test_build_log.py` | Every file is listed in this log. |

### Configuration and tooling

| File | Purpose | Edit? |
|---|---|---|
| `config.yaml` | Every setting in one place: model ids, which model the agents use and the fallback, shipping estimate and tax, risk thresholds, condition multipliers and scores, persona weights, loop limits, data paths, scrape queries and spend cap, search thresholds, live search, Chroma, reply settings, voice settings (Edge-TTS voice, filler lines, silence check, timing log), the web page (port, rows, card cache). Change behaviour here, never by hardcoding. | yes |
| `pyproject.toml` | Defines the project for uv: Python 3.14, runtime dependencies, dev tools (pytest, ruff, pre-commit, ipykernel, nbmake), pytest and ruff settings. Change dependencies with `uv add` / `uv remove`. | rarely |
| `uv.lock` | The exact version of every package, so both laptops and CI install the same thing. | tool (uv) |
| `.python-version` | Tells uv which Python to use: 3.14. | rarely |
| `.env.example` | The names of the three keys (`GEMINI_API_KEY`, `GROQ_API_KEY`, `APIFY_API_TOKEN`); copy it to `.env` and fill them in. | rarely |
| `.gitignore` | What git never commits: `.env`, `.venv`, caches, SQLite files, raw scrapes, `.DS_Store`, the TCGdex set cache. | rarely |
| `.pre-commit-config.yaml` | Pablo's optional git hooks (ruff and pytest before each commit), active only after `pre-commit install`. It pins ruff 0.8.0 while the project uses 0.17.6, so update the pin before relying on it. | rarely |
| `.github/workflows/ci.yml` | GitHub Actions: on every pull request and push to `main`, installs Python 3.14 and the locked packages, runs ruff (lint and format) and pytest, which includes running the notebooks. | rarely |
| `.vscode/settings.json` | Makes VS Code use `.venv`, show the tests in the Testing panel and format with ruff on save. | rarely |
| `.vscode/launch.json` | The Run and Debug entries: "Demo: run sample queries (offline)", "Text chat (offline)", "Text chat (Gemini)", "Run all tests", "Voice chat (Gemini)", "Voice chat (offline agents, real speech)", "Web page (Gemini)", "Voice chat + web page (Gemini)" (the last two to be added by hand), and a placeholder for the ablations (not built yet). | yes |

### Docs

| File | Purpose | Edit? |
|---|---|---|
| `README.md` | The GitHub front page: what the project does, the four agents, setup, how to run it. | yes |
| `BUILD_LOG.md` | This file: status, how it runs, what every file is for, and the change log. Update after every change. | yes |
| `docs/decisions.md` | One line per decision: date, what was decided, why. | yes |
| `eval/schema.py` | Pablo's list of the `results.csv` columns (accuracy, scam recall, policy violations, latency, tokens, cost, ...); the runner (notebook 08) writes these first, then a few of its own. | yes |

### Files that exist only on your machine

Not in git, so they don't appear on GitHub. Created as you work.

| File or folder | What it is |
|---|---|
| `.env` | Your API keys. Never commit it. |
| `.venv/` | The Python 3.14 environment uv builds from `uv.lock`; it's the notebook kernel to pick. Rebuild with `uv sync`. Keep only this one environment. |
| `.cache/llm/` | Saved LLM responses, so re-running a cell doesn't call the API again. Delete it to force fresh calls. |
| `.cache/chroma/` | The red-flag search index, built on the first live run. |
| `.cache/voice/` | The filler, search and progress clips from Edge-TTS, made on the first voice run. Delete it after changing the voice or the lines. |
| `.cache/identified/` | Cards the LLM already identified, by model and listing text, so a listing seen before costs no LLM call. Delete it to identify everything again (for example after changing the identification prompt). |
| `eval/results/` | One folder per evaluation run: results.csv, replies.jsonl, run.json, and after `judge`/`stats` judge.jsonl, summary.csv, comparisons.csv, by_category.csv, report.md. Commit the final runs for the report. |
| `.cache/eval_audio/` | The Edge-TTS recordings of the benchmark requests for the speech-to-text test. Safe to delete. |
| `.cache/cards/` | Rarity, picture link and TCGplayer product id of each card shown on the web page, from TCGdex. Safe to delete. |
| `eval/voice_runs.jsonl` | The voice timing log: one row per spoken turn. Commit it after the 5 timed runs. |
| `data/buyer_memory.sqlite` | Buyer profiles and request history from the chat and the graph. Delete it to start with no memory. |
| `data/raw/snapshot_*.json`, `data/raw/live_*.json` | Raw Apify results with listing links and locations (no seller names: the scraper doesn't return them). A snapshot file is what `--replay` uses. |
| `data/tcgdex_sets.json` | Cached list of TCGdex sets. |
| `data/listings.json`, `data/prices.json`, `data/listings_review.csv`, `data/live_listings.json` | Written by the pipeline and live search once you scrape. These are anonymized and meant to be committed after the hand check. |
| `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.ipynb_checkpoints/`, `.DS_Store` | Caches from Python, pytest, ruff, Jupyter and macOS. Safe to delete. |

## Change log

Newest first.

### 2026-11-26 · Dark theme for the web page

**Why:** asked for. The page now has a dark theme only; there is no light/dark switch.

**What changed:** only the CSS in `src/web/index.html`; the markup and script are unchanged.
- The colour variables now hold a dark palette. The navy that was the text colour is now the panel colour, on a darker base (`#121827`). The green and red are lighter so they stay readable on dark, and the yellow price sticker is unchanged.
- Colours that were written straight into the CSS now use variables. That covers white text on buttons, the white sleeve around the card picture, row hover and the open-row background. The new variables are `--you` (your chat bubbles), `--solid`/`--on-solid` (Send and the selected tab), `--on-felt`, `--hover`, `--inset` and `--bar` (funnel and score bars).
- `color-scheme: dark` makes the scrollbars and form fields dark too.
- All text passes WCAG AA contrast (4.5:1 or more). The faintest grey is 4.9:1 on the panels.

**Checked:** headless Chrome screenshots of a sample search at desktop and phone widths, with a table row opened and the microphone recording; no colours from the old light theme remain.

**Files:** `src/web/index.html`. **Tests:** 16 page tests passing (`tests/test_ui.py`); no Python changed, so nothing else to rerun.

### 2026-11-26 · Evaluation pilot on the Mac (free tier)

**Why:** check that the evaluation works end to end on real models, see the first numbers, and price the paid run before spending anything. Everything below ran on Groq's free tier and Edge-TTS: $0.012 in all.

**The full system, dev split** (`eval/results/20261126_113135_pilot`, 26 items: 22 queries and 4 memory-script turns, 1 repeat, `--model small`, i.e. gpt-oss-20b for every agent):

| Measure | Result |
|---|---|
| Top-1 accuracy | 58% (95% CI 38–77%); simple 67%, complex 64%, price checks 60%, memory turns 25% |
| Top-3 accuracy | 77% |
| A scam among the 3 spoken picks | 50% of answers |
| Scam recall (bait scams kept out of the picks) | 75% |
| Honest-decoy false positives | 50% (only 2 dev queries have an honest decoy as the only answer) |
| Made-up dollar amounts | 0% |
| Memory turns right without asking again | 1 of 2 |
| Naturalness / helpfulness (judge) | 3.9 / 4.6 out of 5 (judge: $0.003); the lowest scores say "stiff and list-like" |
| Median latency | 17.3 s, p90 26 s: mostly waiting on Groq's free-tier tokens-per-minute limit, not representative |
| Tokens and cost per query | 2,609 tokens, $0.0003 |

What the misses show:
- **The new-wording scams cause most of the errors.** The dev queries search the whole pool, so they meet the test-split traps too. The "premium print" Base Set Charizard was the top pick for S01 and C01, the "printed it myself" Pikachu for S05 and C06, and the "Apple Cash up front" Charizard ex was an alternative for C16, C21 and C23. The scam check (keywords and price) doesn't see them; growing the red-flag knowledge base is the fix to test.
- **A parsing miss.** C10 ("Lugia V alt art, serious collector here, condition matters, under $115") found nothing with the small model, although 4 listings fit.
- **Memory.** In M01 the collector carried over correctly; one second turn still went to a missed scam.

**Speech to text** (`eval/results/20261126_113213_voice`, 5 dev requests × 4 Edge-TTS voices, Groq Whisper, with and without the card-name vocabulary):

| | Word error rate | Key words heard (card, set, amount) | Median time |
|---|---|---|---|
| With the vocabulary prompt | 8.5% | 95% | 2.1 s |
| Without it | 14.3% | 88% | 1.9 s |

- The vocabulary helps most for the Indian English voice: errors drop from 20% to 4%, key words rise from 80% to 100%. Without it, "Base Set" became "Bayset" and "Bayes set".
- **A failure the vocabulary doesn't fix:** "Mew ex" was heard as "New X", "Nuwix" or "Muex" in every voice. A spoken Mew ex request would look for the wrong card.
- Smaller misses: "holo" became "Hollow" and "alt art" became "Altart".

**The scraping pipeline on the 28 labeled sample listings** (gpt-oss-20b identification plus real TCGdex set and price checks):
- Scope decisions: 100% precision and 100% recall (graded, lots and Japanese dropped, all 24 singles kept).
- Card name, set and number: 100% right. Condition: 96%; the one miss is "played", read as HP where the label says MP.
- Variant: 71%. The modern cards (151 SIRs, Pikachu VMAX) come back as "normal" where the label says "holo", and so does one Base Set Charizard. Prices still resolved for all of them; the variant only matters when a card has several printings.
- Speed and cost: 2 LLM calls, 0.11 s per listing, $0.0008 for all 28.

**The paid run's estimated cost** (`estimate`, tokens per query from this pilot; the single agent's prompt measured directly, about 12,800 tokens; 3 repeats, all 11 variants):

| Scope | Cost at Gemini 3.8 Flash's price until Dec 31 |
|---|---|
| Test split (34 items) | about $6.60 |
| Both splits (60 items) | about $11.60 |

The biggest single item is the frontier single pass, $2.92 on the test split. Gemini's thinking tokens aren't in a Groq pilot, so the real cost will be somewhat higher; it is still well inside the $25–30 budget. From January 1, Flash costs twice as much.

**Files:** BUILD_LOG only (the results folders are in `eval/results/`, not committed yet).

### 2026-11-26 · Evaluation set-up: benchmark, ablation runner, judge, statistics, pipeline and voice

**Why:** the evaluation is the core of the plan and wasn't built. Gaurav asked for everything needed to measure the system: a single-agent baseline, small and big models, each component switched off, voice-to-voice accuracy and latency trade-offs, and how good the scraping pipeline is.

**Assumptions** (Gaurav didn't pick, so these were taken; both are easy to change):
- **Test pool:** a synthetic benchmark now (its truth is known, so it has an answer key). The real snapshot gets the same treatment after its hand check; the runner takes any pool and query file in this format.
- **Running:** everything built and dry-run offline. The first pilot on Groq's free tier is the entry above; no paid calls yet.

**The benchmark** (`src/benchmark.py`, files in `eval/data/`, frozen; a test checks they match the code):
- 100 listings across 10 real printings (Base Set Charizard, Blastoise, Venusaur, Mewtwo, Pikachu; 151 Charizard ex and Mew ex; Evolving Skies Umbreon VMAX; Silver Tempest Lugia V; Surging Sparks Pikachu ex). Each has 4 clean listings, one of them a genuinely good deal; 3 traps; and 3 decoys (honest but odd: "need it gone today", "not a proxy", "custom sleeve included", a stock photo plus real ones, damaged and priced for it). Ids are a fixed shuffle, so an id says nothing about the label.
- Dev split: 16 traps that use the red-flag knowledge base's wording. Test split: 14 traps in new wording ("premium print", "Apple Cash up front", "reach me on Signal", "bank transfer, I'm travelling"). The test traps measure generalization; tune the knowledge base on dev only.
- 50 queries in MACDF's mix (15 simple, 25 complex, 10 consultative; 22 dev, 28 test): buyer types, conditions, clarification (an ambiguous printing, a missing budget), nothing-fits cases, traps as bait. Also 5 two-turn memory scripts.
- The answer key comes from an oracle that only uses the ground truth (right card, condition, budget, not a trap), with its own weights per buyer type for value, condition and the safety a buyer can see. Acceptable top picks: within 0.08 of the best. Of the 37 recommend queries, 26 have clean and decoy answers, 9 only an honest decoy (these catch false scam alarms), 2 only clean.
- The first answer key made decoys the right answer almost everywhere (they were the cheapest and safest-looking). Fixed by making one clean listing per printing a real deal and weighting condition first for collectors; recorded in `docs/decisions.md`.

**The runner** (`src/evaluation.py`, `python -m src.evaluation run|judge|stats|estimate|screen|rating-sheet|agreement|build`):
- 11 variants in `evaluation.variants`, each changing one thing:
  - `full`;
  - `single_agent`: one LLM call that sees every listing with the same tool outputs (market price for its condition, scam risk and red flags, landed cost, seller signals);
  - `frontier_single` (plan ablation 6), `small_model` (5), `no_reflection` (3);
  - `no_rag`, `no_clarify`, `no_number_check`, `template_reply`, `no_memory`, `plan_scoring`.
- Writes `results.csv` (eval/schema.py's columns first), `replies.jsonl` and `run.json` per run. Metrics: top-1/top-3, correct refusals, policy violations, traps recommended, scam recall, false positives on honest decoys, arithmetic errors (checked independently of the Humanizer's own check), memory turns right without asking again, latency (real calls only), tokens, cost.
- The judge (gpt-oss-120b, another family than Gemini) rates naturalness and helpfulness; `rating-sheet` gives 20 replies for two people to rate, and `agreement` gives Spearman and within-1-point agreement.
- `stats` gives bootstrap 95% intervals over queries, a paired comparison of each variant with `full` (change in top-1 accuracy with its interval, exact McNemar test), results by query type, and `report.md`.
- `estimate` prices a full run from a pilot's tokens, at each variant's model. Prices are in `evaluation.prices_per_million`, checked 2026-11-26: Gemini 3.8 Flash is $0.75 / $3.75 per million tokens until Dec 31, then $1.50 / $7.50.
- `--max-cost` stops a run at a cap. There's no quota fallback during a run, so a run never switches models. 3 LLM errors in a row stop the run. Repeats are part of the cache key.

**Pipeline and voice:**
- `src/eval_pipeline.py`: `health` (the scrape without labels: usable share, duplicates, placeholders, field coverage), `sheet` (the hand-check sheet, pre-filled by the pipeline) and `score` (scope precision and recall, each identity field's accuracy, fully right, price coverage, time and cost per listing). `eval/data/sample_raw_labels.csv` labels the 28 sample raw listings.
- `src/eval_voice.py`:
  - `stt`: the requests spoken by 4 Edge-TTS voices (US ×2, UK, Indian English), transcribed by Whisper with and without the vocabulary prompt; reports word error rate, entity recall and time. With `--agents`, it also compares the spoken requests' top picks with the typed ones.
  - `timing`: H5 from the voice chat's log.
  - `tts`: Edge-TTS time to the first sentence of real replies.

**Found by the offline dry run** (all 11 variants on the dev split, no errors):
- **A bug, fixed:** "What's a fair price for a moderately played Base Set Venusaur?" (a price check with no asked price) got the template reply "A moderately played one usually goes for about $84.00". That fails the number check's card-name rule, so the turn crashed instead of answering. Offline mode, and any time the LLM reply fails, hit it. The template now names the card; regression test in `tests/test_humanizer.py`.
- **The scam check:**
  - dev traps: 100% caught (81% rejected);
  - test traps: only 21% caught. 11 of 14 traps in new wording get through;
  - honest decoys rejected: 7% on dev, 20% on test ("custom", "unofficial" in sleeve descriptions match the fake-card flag).

  This is what growing the knowledge base should fix, and the test split will show whether it does.

**For VS Code** (paste into `.vscode/launch.json`; it replaces the old "Run ablations (not built yet)" entry):

```json
{ "name": "Evaluation: dev run (offline)", "type": "debugpy", "request": "launch", "module": "src.evaluation",
  "args": ["run", "--variants", "all", "--split", "dev", "--model", "offline", "--label", "offline"],
  "cwd": "${workspaceFolder}", "console": "integratedTerminal", "envFile": "${workspaceFolder}/.env" },
{ "name": "Evaluation: final run (paid, capped)", "type": "debugpy", "request": "launch", "module": "src.evaluation",
  "args": ["run", "--variants", "all", "--split", "test", "--repeats", "3", "--max-cost", "25", "--label", "final"],
  "cwd": "${workspaceFolder}", "console": "integratedTerminal", "envFile": "${workspaceFolder}/.env" }
```

**Files:** `src/benchmark.py`, `src/evaluation.py`, `src/eval_pipeline.py`, `src/eval_voice.py` and `notebooks/08_evaluation.ipynb` (new), `eval/data/*` (new), `src/agents/humanizer.py` and notebook 05 (template fix), `config.yaml` (`evaluation`), `tests/test_evaluation.py` (new), `tests/test_humanizer.py`, `README.md`, `docs/decisions.md`. **Tests:** 157 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-26 · Microphone in the web page

**Why:** the page worked (Gaurav tried it on his Mac), and chatting with it should also work by voice, not only by typing or through the terminal.

**What changed for the buyer:**

- A microphone button next to the message box: click, talk, click again to send (Esc cancels). A ring around it grows with how loud it hears you, and the box shows "Listening 0:04". Too short or silent recordings are caught in the page with a hint (the macOS microphone setting for silence).
- The recording is transcribed on the server with the voice chat's `Transcriber` (Groq Whisper with the card-name vocabulary, Gemini if Groq fails); the transcript shows as your message, marked "spoken", and the turn runs as usual.
- For a spoken turn, the page reads aloud, in the voice chat's Edge-TTS voice: the casual lines during a live search ("Hold up a sec while I swim the internet for you!", a line per step, a still-working line after 25 s of quiet), the filler when the listings are checked, then the reply sentence by sentence (each fetched while the one before plays). If Edge-TTS fails, the browser's own voice reads that line. Typed turns stay silent.
- "Read aloud: on/off" at the top of the chat (remembered by the browser); "Stop" while it talks; clicking the microphone also stops it.

**Changes:**

- `src/ui.py` (notebook 10): `PageVoice` (transcribes a recording by its browser type, WebM, MP4 or Ogg; makes the MP3 of a line, with the fixed lines cached in `voice.clip_cache`, shared with the voice chat, and made at startup), `Narrator` (the voice chat's waiting lines as notes the page reads), `BrowserChat.submit_audio()` and `spoken()`, `/api/voice` and `/api/speech`, `--no-mic`. Notes and replies of a spoken turn carry what to read aloud; replayed events (after a page reload) are never read again.
- `src/voice.py` (notebook 09): `Voice.mp3()` split out of `Voice.clip()` (same behaviour), so the page gets the raw MP3.
- `src/web/index.html`: the microphone (MediaRecorder, a level meter from the Web Audio API), the read-aloud queue, "Read aloud" and "Stop".
- `serve()` and `open_page()` now take the `BrowserChat` itself instead of its `submit` function.

**Tested:** 5 new tests (127 in all), and the whole path in headless Chrome with a fake microphone: an 18.7 KB WebM recording was sent, transcribed (a stand-in for Whisper), narrated (the filler) and its 3 reply sentences requested from `/api/speech`. The microphone needs Chrome or Safari on the same computer (127.0.0.1 counts as secure); the first click asks for permission.

**Tried on the Mac** (Groq agents, the replayed scrape, real Groq Whisper and Edge-TTS; the spoken messages were Edge-TTS recordings sent to `/api/voice`, the way the page sends a recording): "Hi, I'm looking for a Base Set Charizard under five hundred dollars, and I care about condition" came back word for word as "...under $500...", and the read-back came with its two sentences to read aloud. A spoken "Yes, go ahead." then gave the search line, both progress lines and the filler, the reply in sentences and the results: 1.4 s from transcribing to results (the identified cards were cached). One reply sentence from `/api/speech` took 0.89 s (24.6 KB of MP3). The page showed the "spoken" labels and the lines said during the search. **Not tried yet:** a real microphone in the browser, which needs someone to talk.

**Files:** `src/ui.py`, `src/voice.py`, `src/web/index.html` and notebooks 09 and 10; `tests/test_ui.py`; `README.md`, `docs/decisions.md`. **Tests:** 127 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-25 · Local web page: the chat, the agents at work, the results

**Why:** to watch the system work while it runs, and to see every result with its details instead of only the spoken top 3.

**What you see** (`python -m src --ui`, or `--voice --ui` to talk while the page follows along; layout under [The web page](#the-web-page---ui-notebook-10)):

- The conversation, typed or spoken, including the casual lines said while a live search runs, and a "Yes, search" button at the read-back.
- Each graph step as it runs, with a live timer; the live search's steps ("Searching Facebook Marketplace for ...", "Got 78 listings, 65 of them real ones", "Identified 11 single cards"); the parsed request.
- How the search narrowed down: scraped, real listings, past the title check, identified, matching the request, passing the budget and safety rules, and why the rest were left out.
- The top pick, shown like a card in a sleeve with the total on a price sticker: card picture, condition, rarity, the market value for its condition (and near mint, with the variant), where that value comes from (TCGplayer market price via TCGdex, its date and a TCGplayer link), the seller's city and distance, when it was listed, pickup or shipping, public meetup, photos, the score of 100 with how it adds up, the reasons and any red flags, and a link to the listing on Facebook. Then the two alternatives the assistant mentioned.
- All ranked listings in a table that sorts by any column and filters by text; a click opens the description, score breakdown and links. The listings that broke a rule are listed with the rule.
- Each search gets its own tab; reloading the page replays the whole conversation.

**Not shown: seller names.** Our scraper (`apify/facebook-marketplace-scraper`) returns none: its 23 fields have no seller at all (checked on the 100-listing scrape), and Apify's community notes say Facebook hides names from logged-out scrapers; the actors that get them need Facebook login cookies. The page shows the seller's side we do have and the listing link.

**Changes:**

- `src/ui.py` (new notebook 10): `LiveBoard`, `listing_row()`, `results()`, `funnel()`, `CardDetails`, `serve()` (Python's `http.server`, server-sent events, 127.0.0.1 only, the next free port if 8765 is taken), `BrowserChat`, `open_page()`, `main()`. No new dependency.
- `src/web/index.html` (new, hand-written): the page. Gill Sans (the face printed on Pokémon cards, already on every Mac) with system figures for prices; no build step; card pictures from TCGdex's image server, everything else local.
- `src/graph.py` (notebook 07): `on_task(name, phase, info)` gets a third argument, the progress details (search term, counts).
- `src/agents/merchant.py` (notebook 04): the live search summary keeps each fresh listing's Facebook link (`links`), in memory only; `data/live_listings.json` still has none.
- `src/voice.py` (notebook 09): `VoiceChat(board=...)` sends the transcript, the lines said during the search, the reply and the results to the page (the results on their own thread, so speaking never waits for card details); `--ui`, `--port`, `--no-browser`.
- `src/__main__.py`: `--ui` starts the web page. `config.yaml`: new `ui` section.
- Card rarity, picture and TCGplayer product id come from each card's TCGdex record, fetched after the reply and only for the cards on the page, cached in `.cache/cards`.

**Tried on the Mac** (Groq gpt-oss-20b for every agent, the replayed 100-listing scrape, the page in the Claude app's browser): greeting, small talk, the request, the read-back, "yes", then a price check typed in the page. The page showed the steps with their timers and the funnel 78 → 65 → 18 → 11 → 4 → 3, with the 52 left out by reason. The top pick showed its TCGdex picture, rarity Rare, $700.73 market value for moderately played ($1,001.05 near mint, holofoil; TCGplayer market price via TCGdex, updated Nov 24, 2026, with the TCGplayer link), Norwalk, OH, 79 miles away, listed 27 days ago (Oct 29), local pickup with a public meetup, and the link to the listing. The price check opened a second tab with its market value ($850.89 lightly played). No errors in the page's console; 122 tests pass on the Mac.

**For VS Code's Run and Debug panel** (tool access can't write `.vscode/`, so paste these into `configurations` in `.vscode/launch.json`):

```json
{ "name": "Web page (Gemini)", "type": "debugpy", "request": "launch", "module": "src",
  "args": ["--ui"], "cwd": "${workspaceFolder}", "envFile": "${workspaceFolder}/.env", "console": "integratedTerminal" },
{ "name": "Voice chat + web page (Gemini)", "type": "debugpy", "request": "launch", "module": "src",
  "args": ["--voice", "--ui"], "cwd": "${workspaceFolder}", "envFile": "${workspaceFolder}/.env", "console": "integratedTerminal" }
```

**Files:** `src/ui.py`, `src/web/index.html`, `notebooks/10_interface.ipynb` (new); `src/graph.py`, `src/agents/merchant.py`, `src/voice.py` and notebooks 04, 07, 09; `src/__main__.py`; `config.yaml` (`ui`); `tests/test_ui.py` (new), `tests/test_live_search.py`, `tests/test_voice.py`; `README.md`, `docs/decisions.md`. **Tests:** 122 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-25 · Faster identification, casual replies

**Why:** in the replay run, 36–47 of the 56 seconds before the answer were spent identifying the 65 listings in 4 LLM calls made one after another. And spoken replies ran 15–25 seconds and sounded like a report.

**Faster** (notebook 02, used by the snapshot ingest and the live search alike, through the new `identify_listings()`):

- **Title pre-filter** (`prefilter()`, `ingest.prefilter`): drops graded slabs ("PSA 9", but not "PSA 10 worthy"), lots, binders, booster packs and boxes, and non-English cards by their title, before any LLM call. In a live search it also drops listings whose title and description never name the card (fuzzy, so "Charzard" still counts). On the 100-listing scrape it dropped 21 of the 65 usable listings (10 graded, 7 lots or sealed, 4 non-English) and none of the 26 cards the LLM kept. For a live Charizard search, the 26 listings that never mention Charizard go too, so only 18 reach the LLM: 1 call instead of 4.
- **Parallel batches** (`ingest.parallel_calls`: 4): the identification calls run at the same time, so 100 listings (5 batches of 20) take about one call's time.
- **Identified-card cache** (`IdentifiedCache`, `ingest.identified_cache`: `.cache/identified`): a listing already identified, with the same text and model, isn't sent again. A repeat search, or a re-run of the snapshot ingest, only identifies new or edited listings. Not used in offline mode.
- **`ingest.llm`**: a separate model for identification, e.g. `small` (Groq gpt-oss-20b, 1–2 s per call in our tests); null keeps the agents' model.
- The live search summary and the ingest summary now report what was dropped before and after the LLM, how many cards came from the cache and how many LLM calls ran (`identify`).

**Casual replies** (notebook 05):

- New Humanizer prompt: 2–3 short sentences (about 50 words), the way a friendly regular at a card shop would say it: contractions, a quick reaction is fine, no "I recommend", "Please note" or "Based on". The top pick with why, then the alternatives together in one sentence.
- The template reply (used offline and when the LLM fails) matches: "Your best bet is the Charizard from Base Set, near mint, for $360.00 with local pickup: 25% under the market price and a public meetup offered. Also worth a look: …". A reason that only repeats the condition isn't said twice, and "risky" became "sketchy".
- The "these are sample listings" note is said once per conversation, not in every reply (`sample_note_said`, set by `ChatSession`).

**Measured** (replay of the 100-listing scrape, "a Base Set Charizard under 500 dollars, I care about condition", Groq gpt-oss-20b for every agent with `AGENTIC_LLM=small`, run on the Mac):

- **First search (empty cache):** the pre-filter dropped 47 of the 65 usable listings (10 graded, 7 lots or sealed, 4 non-English, 26 never name Charizard), so 18 went to the LLM in 1 call. The search step took 2.4 s and the whole turn 4.3 s (intent 0.9 s, search 2.4 s, flag check 0.7 s, reply 0.3 s). The replay before these changes took 56 s with Gemini; part of that gain is the faster model, not only the pre-filter. A real live search adds the Apify scrape time on top.
- **Same search again (cache filled):** all 18 cards came from the cache with no LLM call and the search step took 0.8 s, but the turn took 19.3 s because the flag check (4.3 s) and the reply (13.8 s) were slow. No error was logged; most likely the calls waited on Groq's free-tier per-minute token limit, since this run started seconds after the first one.
- Both runs ranked the same 3 listings (11 cards kept). Two things to fix later: the small model's reply mixed "36% below market" with "53% of market" and once said "clear pics", which isn't one of the listing's reasons; and the lightly played $450 listing ranked below a moderately played $450 one because TCGdex's Base Set Charizard price makes it look under 60% of market (a neutral deal score). This is the vintage-price issue already open.

**Researched, not built yet** (prices as listed in November 2026):

- **Start the scrape during the read-back**: hides several seconds, but a correction wastes the scrape (about $1.24).
- **More sources, scraped at the same time as Facebook** (separate Apify runs; each needs its own field mapping): eBay is the best addition because its listings carry seller feedback (count and positive %), which would give the trust score real seller data; Apify eBay scrapers cost about $2–3.50 per 1,000 results, while eBay's own Browse API needs eBay's production approval. OfferUp (local pickup, about $1.50–3.50 per 1,000) and Mercari (shipped, about $2.50 per 1,000, behind Cloudflare) also have scrapers. Reddit's trade subreddits are out: new API access closed on October 31, 2026. All of these are community scrapers with few users.
- **Bigger LLMs are not faster**: speed comes from fewer, parallel, smaller calls; paid keys help by removing free-tier waits and the quota fallback (which ran out on 2026-11-25).
- **A more natural voice**: OpenAI `gpt-4o-mini-tts` takes speaking instructions ("casual, upbeat") at about $0.015 a minute; ElevenLabs Flash v2.5 is the most natural and fastest (about 200 ms measured) at about $0.05 per 1,000 characters, with a 10,000-credit free tier; Gemini 3.8 Flash TTS works with our Google key but took about 4.6 s per request (median). Edge-TTS would stay as the fallback.

**Files:** `src/pipeline.py`, `src/agents/merchant.py`, `src/agents/humanizer.py`, `src/graph.py`, `src/state.py` and their notebooks (00, 02, 04, 05, 07), `config.yaml` (`ingest`), `tests/test_pipeline_offline.py`, `tests/test_humanizer.py`, `tests/test_dialogue.py`, `tests/test_graph_offline.py`. **Tests:** 110 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-25 · Conversation flow, live search, and the 5-part listing score

**What the buyer hears now:**

1. "Hi! I'm your AI card-shopping assistant. How are you doing today?" (the AI disclosure is in the greeting), one line of small talk from the LLM, then "So what cards are we looking for today?". If the reply to the greeting already asks for a card, it goes straight on.
2. At most one clarifying question, then the read-back: "Okay, so just to confirm: you're looking for a Charizard from Base Set, with a budget of $400.00, and condition matters most to you. Is that right?" A yes starts the search; a correction is read back once more (`dialogue.max_confirm_rounds`: 2); a plain no gets "No problem. What should I change?". Price checks are answered without a read-back.
3. With `--live`, a Marketplace search of 100 listings for this request, with casual lines while it runs: "Hold up a sec while I swim the internet for you!", a line as each step finishes, and a "still swimming" line after 25 seconds of quiet. Then the best 3, each with its reasons.

**Changes:**

- **Conversation** (notebooks 06, 07): CONFIRM node; the read-back is built by code from the parsed query, so its numbers are exactly the search's. `read_confirmation()` reads a plain yes by code (no delay) and sends anything else to the LLM, which tells a no from a correction. `smalltalk_reply()`. `ChatSession` keeps the stage (small talk, request, clarify, confirm, correct). A start router sends a confirmed query straight to SEARCHING. The read-back happens only when `ChatSession` asks for it (`confirm_first`), so the tests, the demo and the evaluation runner run the graph as before. The intent prompt now says the latest correction wins. `config.yaml`: `dialogue:` section.
- **Live search** (notebook 04): `--live` (text or voice chat) or `merchant.live`. Each new search scrapes `merchant.live_limit` (100) listings with a $1.50 cap (`live_max_charge_usd`), and the request picks only from those fresh listings; the same search again in a run reuses them. Progress events go through LangGraph's custom stream. `--replay FILE` (`merchant.live_replay`) replays a saved scrape instead of calling Apify: the same path for free. Live mode uses the real data and TCGdex prices, never the sample prices, and searches with the set's name ("base set", not "base1"). `search.max_candidates` went from 15 to 100 so every match is scored.
- **Listing score** (notebook 01): deal (total against the market price for its condition; a price under 60% of market gets a neutral 0.5, not full marks, because the scam check handles it), condition, trust (scam risk plus photos, description, public meetup, listing age, pending), convenience (pickup distance from `buyer`, or shipping) and identification confidence, weighted per buyer type (`scoring.weights`) into 0–100, with the reasons that earned the most points. Plan v2's formula is still there as `scoring.method: plan`. The Humanizer speaks the top pick with why and the next two with their main reason (`response.max_alternatives`: 2); the template does the same and mentions each one's warning.
- **Real-data fixes** (notebook 02): $1 placeholder prices dropped; listing signals kept (photo count, posting date, distance, public meetup, pending; the coordinates are not kept); the printed set size picks the set when only one set has that size; `PriceBook.verify_cards()` checks each card against TCGdex and, when the name doesn't match or the set is unknown, tries every set with that printed size; set-name aliases (`tcgdex.set_aliases`); promo numbers ("XY121") through the set's card list; the review sheet has a "why" column (low confidence, no market price, name matches no card).
- **Flag explanations** now get the red flags found in the listing apart from related background entries, and may only claim the found ones.
- **Voice** (notebook 09): the greeting is spoken at startup; the search, progress and still-working lines (`voice.search_lines`, `progress_lines`, `still_lines`, `still_after_s`); `Speaker.busy`, so optional lines are skipped instead of queued; the timing row adds `to_search_line_s` and the live search's counts and seconds.

**Run on Gaurav's Mac** (`gemini-3.8-flash` free tier, typed and muted, replaying the 100-listing scrape, so no Apify charge):

- The conversation worked as designed: greeting → small talk ("I'm so glad to hear that, welcome in!") → read-back → yes.
- 78 listings → 65 usable (8 $1 placeholders dropped) → 26 cards. TCGdex fixed 3 sets: Sabrina's Gengar is Gym Heroes, Mega Gengar 056/094 is Phantasmal Flames, Team Rocket's Mewtwo ex 231/182 is Destined Rivals. It also caught 1 name that matches no card: "Blastoise 3/102" (3/102 is Chansey).
- Identifying and checking the 65 listings took 36–47 seconds; the answer came 56 seconds after the yes. A paid search adds the Apify run on top.
- **Found and fixed in that run:** a price at 53% of market got full deal points and the reason "about the market price", so a flagged listing was ranked first; the flag explanations claimed "borrowed photos" and "signs of a reproduction" that came from background red-flag entries, not from the listing; the search text was "pokemon charizard base1". After the fixes the clean listing (no risk, 36% under market, public meetup offered) ranks first.
- Gemini's free daily quota ran out during these runs, and the fallback model was rate-limited too, so the last run answered with the template.

**Not tried yet:** a paid live search, and the new conversation with the microphone. **Tests:** 110 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-25 · Voice chat (notebook 09)

`python -m src --voice` (or Run and Debug → "Voice chat (Gemini)") is the voice loop from Plan Section 6, a thin layer around the same `ChatSession` the text chat uses.

- **A spoken turn:** press Enter, speak, press Enter (16 kHz mono through `sounddevice`) → Groq `whisper-large-v3-turbo`, given the card and set names as a vocabulary prompt → `ChatSession.send(text, on_task=...)`, which streams the graph node by node → when EVALUATING starts, one of 5 filler lines plays (made once with Edge-TTS and kept in `.cache/voice`) → the reply is spoken with Edge-TTS (`en-US-AvaNeural`) → one row in `eval/voice_runs.jsonl`: seconds from the end of the recording to the transcript, to the filler and to the answer, plus each stage.
- **When something fails:** Whisper → Gemini transcribes the same audio → you type it. Edge-TTS → macOS `say` (pyttsx3 elsewhere) → printed only. No audio device → printed only. A silent recording isn't sent; the chat says to give VS Code microphone permission.
- **Options:** `--keyboard` (type, hear the reply), `--mute` (print, don't speak), `--offline` (rule-based agents; speech still uses Groq and Edge-TTS), `--audio FILE ...` (recordings as the requests, then exit), `--log`, `--session`, `--db`. `synthesize_requests()` makes test recordings with Edge-TTS.
- **Different from the plan, and why:**
  - Speech-to-text fallback is Gemini, not local faster-whisper: its engine (ctranslate2) has no Python 3.14 build for macOS.
  - The 3-second Edge-TTS limit is on waiting for audio, not on the whole reply: a whole Gemini reply takes 1.8–6.6 s to arrive even when Edge-TTS is fine.
  - The reply is spoken a sentence at a time, each made while the one before it plays: the first sentence is ready in 0.7–1.6 s instead of 1.8–6.6 s for the whole reply.
  - Whisper gets a vocabulary prompt (`voice.stt_vocabulary` plus the pool's card and set names). Without it, it heard "Pikachu" as "Pocaccia", "Mewtwo" as "MuteWO", "Blastoise" as "Blast Toys", "holo" as "hollow".
  - The voice chat doesn't use the LLM cache, so its timings are real calls.
- **Measured on Gaurav's Mac** (Edge-TTS recordings of the sample requests as input, `gemini-3.8-flash` free tier, playback muted):
  - Whisper: 0.15–0.46 s per request. With the vocabulary prompt it got Pikachu VMAX and holo right but still wrote "Blast Toys", "Mewo", "VenaSaur", "Charsard", "bass set" and "The 150-1-1" (for "The 151 one"). The intent step read every one correctly, so no correction step was added. Gemini's fallback transcription took 0.9 s.
  - 5 turns (Q01, Q03 and its clarify answer, Q06 heard as "Blast Toys", Q10): all right, and the clarifying question got no filler. To transcript 0.24–0.34 s, to filler 2.6–4.2 s, to answer 8.4–15.1 s. Before the filler the buyer waits on INTENT (2.3–4.6 s); after it on EVALUATING (1.6–3.2 s) and RESPONDING (1.9–7.6 s).
  - Muted, the answer didn't have to wait for the filler (2–3 s of audio) to finish; with sound it can't start before that.
- **Not tried yet:** the microphone and the speakers (needs VS Code's microphone permission on the Mac), and the 5 timed runs for H5.
- **Files:** new `notebooks/09_voice.ipynb` → `src/voice.py`, `tests/test_voice.py` (13 tests). `src/graph.py` (notebook 07): `ChatSession.send(..., on_task=...)`. `src/__main__.py`: `--voice`. `config.yaml`: `voice:` section, `models.stt_fallback` is now Gemini. `pyproject.toml`, `uv.lock`: `soundfile` 0.14.0 added (decodes Edge-TTS's MP3), `numpy` declared. `.vscode/launch.json`: the two voice entries replace the placeholder (pasted by hand: remote tools can't write `.vscode/`).
- Tests: 76 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-25 · First snapshot: 100 listings

**Code:** `scrape_snapshot()` in notebook 02 (`src/pipeline.py`) runs one Apify search per entry in `scrape.queries`, `scrape.per_query` listings each, keeps a listing found by two searches once, and saves one combined raw file. `config.yaml` now has 10 specific searches (Charizard Base Set holo, Charizard ex 151, Pikachu VMAX, Umbreon VMAX, Blastoise, Venusaur, Mewtwo, Gengar, Lugia, Rayquaza) instead of one broad one, `per_query: 10` and a $2.00 cap for the whole snapshot. `search()` takes `save_as=None` so the per-search results aren't saved separately. New test: `test_snapshot_runs_each_search_and_keeps_listings_once`.

**Run** (Gaurav's Mac, Detroit, Gemini `gemini-3.8-flash` free tier, real TCGdex). Raw file: `data/raw/snapshot_20261125_154037.json` (gitignored). Written: `data/listings.json`, `data/prices.json`, `data/listings_review.csv` (not committed yet; `data.use_samples` is still true).

| Step | Count | Note |
|---|---|---|
| Fetched from Apify | 100 | 10 searches × 10 |
| Unique | 78 | 22 found by two searches (Gengar, Lugia and Rayquaza overlapped most) |
| With a price, not sold or hidden | 73 | |
| Dropped: lots and sealed product | 28 | |
| Dropped: graded | 13 | |
| Dropped: not English | 4 | |
| Dropped: card not identified | 2 | |
| **Kept** | **26** | 33% of unique listings |
| Exact printing and a TCGdex price | 17 | of which 2 are the wrong card (below), so 15 correct |
| Kept, but no market price | 9 | set not identified or not resolved (6), number unknown (2), promo id not found (1) |

- **Kept cards:** Base Set Charizard ×4 ($400–775), Base Set 2 Charizard, Charizard ex 151 ×3, Charizard-EX XY promo, Venusaur ex 151, Umbreon VMAX ×3 (incl. the $2,000 Moonbreon), Neo Discovery Umbreon, Base Set Blastoise, Base Set Venusaur ×3, Team Rocket's Mewtwo ex, Mega Gengar EX ×2, Sabrina's Gengar, Pikachu VMAX ×2, Pikachu ex, the Van Gogh Pikachu promo. Nothing from the Lugia or Rayquaza searches survived the scope filter.
- **Wrong card attached (bug):** "Mega Gengar EX 056/094 PFL" was put in Phantom Forces (`xy4-56`, which TCGdex says is Purrloin, $0.21); PFL is Phantasmal Flames (`me02`, 94 cards). "Sabrina's Gengar 14/132 Gym Challenge" got `gym2-14`, which is Rocket's Mewtwo; the seller named the wrong set (Sabrina's Gengar is Gym Heroes 14/132). The pipeline doesn't compare the identified card name with the name TCGdex returns, so both rows carry another card's market price. Fix: drop the price and flag the row when the names differ.
- **Placeholder price:** "Venusaur Base Set!!!" is listed at $1 against a $133.88 market price. Like the $0 "make an offer" posts, $1 is a placeholder, and it would look like a scam to the risk score. Fix: drop listings at $1 or less.
- **Sets the run missed but could have found:** the printed total names the set. "Team Rocket's Mewtwo ex 231/182" is Destined Rivals (`sv10`, 182 cards) and "056/094" is Phantasmal Flames (`me02`, 94), but the set was left unknown or guessed. The Van Gogh Pikachu was identified as "Scarlet & Violet Black Star Promos", which TCGdex calls "SVP Black Star Promos", so the name didn't resolve. The Charizard-EX promo resolved to `xyp` but the lookup used number `121`, and TCGdex numbers XY promos `XY121`.
- **Seller typo corrected:** "Blastoise 3/102" was identified as `base1-2` (Blastoise is 2/102; 3/102 is Chansey). Right, but worth a look in the hand check.
- **Review list is too short:** the run flagged 4 rows (confidence below 0.7), but 5 more rows with no market price and the 2 wrong-card rows also need a look. `unpriced` in the summary only counts failed price lookups, not rows that never had a set or number.
- **LLM:** 4 calls (20 listings each), 10,822 tokens in, 8,704 out (most of it thinking at `thinking_level: low`). About $0.04 at paid Gemini prices.
- **Apify cost: $1.24** (10 runs × $0.124), so $0.0124 per listing. The actor charges $6.20 per 1,000 listings on the Free plan, plus the same again for listing details (`include_listing_details: true`), which we need for the description. The $2.60 per 1,000 used in earlier estimates is the Business-plan price without details. The 10-listing test on 2026-11-24 cost $0.12, not the $0.03 logged there. Spent so far: $1.36 of the Free plan's $5 monthly credit. Duplicates are paid for too: $1.24 bought 78 unique listings and 26 usable cards, about $0.05 per kept card.
- Tests: 62 passing (offline), ruff clean, notebooks match `src/`.

### 2026-11-24 · First real scrape: 10-listing test

Search "pokemon charizard card", Detroit, 10 listings, through Apify ($0.12 of the free credit; first logged as $0.03), then Gemini card identification and TCGdex prices, on Gaurav's Mac. Outputs went to `data/raw/` (gitignored), not to `data/listings.json`.

- **The actor's real field names differ from the ones we had assumed:** `listingTitle`, `listingPrice.amount`, `description.text`, `condition`, `deliveryTypes`, `locationText.text`, `listingPhotos`, `isSold`, `isHidden`. No seller name comes back. `anonymize()` (notebook 02) now reads these, and still accepts the old names.
- **Result:** 10 raw → 6 with a price (4 were "make an offer" at $0) → Gemini identified all 6 in one call (1,090 tokens in, 543 out) → the scope filter dropped 4 lots or sealed boxes and 1 PSA-graded card → **1 usable single card**: Base Set Venusaur 15/102 holo, heavily played, $60. TCGdex resolved Base Set to `base1` and returned a real TCGplayer market price ($133.88 for the holo), so the price check runs on real data.
- **What this means for the snapshot:** broad searches return mostly lots, sealed product, graded cards and "make an offer" posts. Getting about 100 usable single cards needs more specific searches (card name plus number, for example "charizard 4/102") and more raw listings. Plan: one more small test with specific searches to measure the usable rate, then size the full scrape. (The $2.60 per 1,000 listings assumed here was wrong; see 2026-11-25.)
- **Facebook's condition label** ("New", "Used - like new", ...) is now passed to the card identification as a weak hint, used only when the title and description say nothing about condition: New → NM, Used - like new → LP, Used - good → MP, Used - fair → HP. It is not stored.
- `data/samples/sample_raw_listings.json` now uses the real field names; `tests/test_pipeline_offline.py` checks both formats.
- Tests: 61 passing.

### 2026-11-24 · First real AI calls (free Gemini and Groq keys)

Run on Gaurav's Mac with the free-tier keys in `.env`; the cloud sandbox can't reach these APIs.

- **Key check:** all four models answer, plain text and structured JSON (the intent schema): `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`.
- **Full demo, live** (`python -m src --demo`, the 10 sample queries):

| Model | Result | Time per query | LLM calls | Tokens in / out |
|---|---|---|---|---|
| gemini-3.8-flash (thinking low) | 10/10 | 4–20 s, about 10 s on average | 32 (3 cached) | 11,794 / 2,210 |
| openai/gpt-oss-20b (Groq, reasoning low) | 10/10 | 1–2 s, up to 16 s when Groq's free rate limit makes it wait | 32 (3 cached) | 19,139 / 2,959 |

  No call fell back to the free-tier model; every reply was written by the LLM (no template fallback) and passed the number check.
- **Measured cost:** about 1,200 input and 220 output tokens per query on Gemini 3.8 Flash, roughly $0.002 per query at paid prices, well below the estimate in the project guide.
- **Thinking level matters:** on 3.8 Flash, thinking `low` took 4.4 s and 60 output tokens per intent call; the model default took 8.7 s and 390 tokens, with the same answers. `minimal` is rejected by 3.8 Flash.

Changes:
- `src/llm.py` (notebook 00): `thinking_level` setting (`config.yaml` `llm.thinking_level: low`) sent as Gemini's thinking level and as gpt-oss `reasoning_effort` on Groq; Gemini thinking tokens now count as output tokens (they are billed as output).
- `src/agents/humanizer.py` (notebook 05): for a price check the reply answers the question first (asked price vs market), then mentions a listing. Live, the first version led with a listing.
- `src/graph.py` (notebook 07): the demo prints seconds per query and who wrote the reply, ends with the LLM usage, and passes a price check when the reply states the market price (it used to look for the template's wording, which a real model doesn't use).
- `tests/test_graph_offline.py`, `notebooks/07` demo cell: same price-check rule.
- Tests: 61 passing (offline).

### 2026-11-24 · File guide rewritten

- `BUILD_LOG.md`: [Project structure](#project-structure) now shows every file; [What each file does](#what-each-file-does) gives each file's purpose and how it is meant to change, grouped by notebooks, `src/`, data, tests, configuration and docs, plus a table of the files that exist only on your machine.
- `tests/test_build_log.py` also checks `.python-version` and `data/raw/.gitkeep`.
- `data/red_flags.md`: header now names the right config key (`thresholds.red_flag_severity`).
- Tests: 61 passing.

### 2026-11-24 · Runs from VS Code's Run and Debug panel

- `src/graph.py` (notebook 07): `main()` and `run_sample_queries()`: a terminal chat, and a demo that runs the 10 sample queries and prints PASS/FAIL for each.
- `src/__main__.py` (hand-written, 3 lines): `python -m src` calls `main()`. Flags: `--offline` (no API calls), `--demo` (sample queries), `--session`, `--db`.
- `.vscode/launch.json`: working configurations "Demo: run sample queries (offline)", "Text chat (offline)", "Text chat (Gemini)", "Run all tests". Pablo's voice and ablation entries are kept and marked "not built yet".
- `tests/test_graph_offline.py`: the entry point runs the demo (10/10) and a chat turn.
- Tests: 61 passing.

### 2026-11-24 · Project moved to Python 3.14

- `.python-version` 3.12 → 3.14; `pyproject.toml` `requires-python` `>=3.12,<3.13` → `>=3.14,<3.15`, ruff `target-version` `py312` → `py314`; `.github/workflows/ci.yml` installs 3.14.
- `uv.lock` re-resolved for 3.14. No package version changed; every package has 3.14 wheels for macOS arm64 and Linux (checked), and Chroma/onnxruntime work on 3.14.
- Code: `src/llm.py` (notebook 00) drops the quotes in `fallback: LLM | None`, which 3.14's lazy annotations allow (ruff UP037). `src/nbexport.py` uses 3.14's `except SyntaxError, IndexError:` form, as ruff formats it for py314. Setup-cell message now says `.venv (Python 3.14)`.
- `pyproject.toml`: pytest ignores one 3.14 deprecation warning raised inside langsmith (a langgraph dependency).
- After pulling: run `uv sync` (it rebuilds `.venv` on 3.14), then pick the `.venv` kernel in each notebook.
- Tests: 60 passing on 3.14, ruff clean.

### 2026-11-24 · Kernel check in every notebook's setup cell

`notebooks/00`–`07`: the setup cell now checks that `yaml`, `dotenv`, `langgraph` and `pydantic` can be imported before anything else runs. If VS Code picked a kernel other than the project's `.venv`, the notebook stops with a message naming that kernel and saying how to switch, instead of a bare `ModuleNotFoundError: No module named 'yaml'` in the config cell. No exported code changed. Tests: 60 passing.

### 2026-11-24 · Pablo's code reviewed, moved into notebooks; pipeline, Merchant and Humanizer added

**Review of Pablo's code.** The contracts, tools, graph and memory follow Plan v2 and are kept. Bugs found and fixed:

1. Saved persona overrode the persona stated in the message (`agents/consumer.py`). The intent LLM no longer sees the profile and returns `persona: null` when unstated; `apply_memory()` fills only gaps and records them in `ParsedQuery.filled_from_memory`.
2. RANKING crashed with no budget: on consultative questions, and when the buyer still gave none after the one clarifying question. `evaluate_policy` and `rank_listings` accept `budget=None` (the budget rule is skipped); the Merchant adds price-check facts for consultative questions.
3. The printing question could never fire (`agents/platform.py`, unreachable condition). `needs_clarification()` now takes the printings found by the Merchant.
4. `scripts/ingest.py` couldn't run against the Apify actor or apify-client 3.x, had no spend cap, stored descriptions as `"{'text': ...}"`, used row-number ids, turned missing prices into $0, made one LLM call per listing and looked up TCGdex with raw model output. Replaced by notebook 02.
5. Ruff (0.17.6, locked) reported 56 issues, so CI would fail. Fixed; ruff check and format pass on code and notebooks.
6. The intent call used `ParsedQuery` as the Gemini response schema; its `budget` has `gt=0`, which the Gemini SDK rejects (`exclusiveMinimum`), so the first live call would have failed. The LLM now gets `IntentExtraction` (no such constraint), and `tests/test_llm.py` converts every structured-output schema the way the SDK does.
7. Frontier model id corrected to `gemini-3.1-pro-preview`.

**Added:** `notebooks/00`–`07` with `src/nbexport.py`; `src/llm.py`; `src/pipeline.py`; `src/tools/prices.py`, `src/tools/risk.py`; `src/agents/merchant.py`, `src/agents/humanizer.py` (replacing the stubs in `graph.py`); `ChatSession`; sample data in Pablo's `CardListing` schema; `data/red_flags.md`; 9 new test files; this log.

**Schema additions (all optional, defaults keep old code working):** `CardListing.set_name`, `CardListing.card_key`; `ParsedQuery.variant`, `any_printing`, `asked_price`, `filled_from_memory`; `AgentState.price_check`, `live_search`, `response_source`.

**Config additions:** `models.offline`, `llm`, `thresholds.red_flag_severity`, `thresholds.price_check_fair_max`, `data`, `scrape`, `ingest`, `tcgdex`, `search`, `merchant`, `rag`, `response`. Pablo's values unchanged.

**Removed:** `scripts/ingest.py` (now notebook 02), the per-agent Gemini clients and caches (now `src/llm.py`), the graph stubs.

**Tests:** 60 passing (Pablo's 16 unchanged and passing, plus 44 new), all 8 notebooks run offline, ruff clean.

### 2026-11-23 · Day 1 contracts, tools, Consumer and Platform agents (Pablo)

Shared interfaces (`src/state.py`, `src/schemas.py`), `config.yaml`, deterministic tools (landed cost, utility, policy), SQLite memory, Consumer and Platform agents, the 7-state graph with stubs for Merchant and Humanizer, `scripts/ingest.py`, CI, VS Code settings. 16 tests.

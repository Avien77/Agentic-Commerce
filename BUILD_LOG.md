# Build log: Agentic Commerce

**Last updated:** 2026-11-24 · **Branch:** `main` · **Tests:** 60 passing · **Notebooks:** all 8 run top to bottom offline

This file records how the project is built and how it runs, what every file is for, and what changed when. Read it before touching the code.

## Keeping this log current

After every change, before you commit:

1. Add an entry at the top of the [Change log](#change-log): the date, what changed, which files, why, and the test status.
2. If you added, removed, renamed or repurposed a file, update [Project structure](#project-structure) and [What each file does](#what-each-file-does).
3. If something started or stopped working, update [Current status](#current-status) and the header line above.

`tests/test_build_log.py` fails if a notebook, module, test, config or data file is missing from [What each file does](#what-each-file-does), so a new file can't be added without logging it. One-line decisions also go in `docs/decisions.md`.

## What the project is

A voice-to-voice multi-agent assistant for buying single Pokémon cards on Facebook Marketplace. It works out exactly which card each listing is, checks the price against TCGdex market data, flags likely scams, ranks the remaining listings for the buyer's persona, and answers in short natural speech. Four agents (Platform, Consumer, Merchant, Humanizer) share one LangGraph state graph. It is a course project run from VS Code; there is no app or website. The plan is the "Project Plan v2" doc.

Pablo built the shared contracts (config, schemas, state, memory), the deterministic tools, the Consumer and Platform agents and the graph. Gaurav's side built the data pipeline, the Merchant and Humanizer agents and the shared LLM client, moved all code into notebooks, and fixed the bugs listed in the 2026-11-24 entry.

## Current status

**Works (offline, on sample data, tested):**

- The full graph: request parsing, at most one clarifying question (missing budget or several printings), search with one relaxed retry, risk scoring with flag explanations, policy rules, ranking, a number-checked spoken reply with template fallback, and memory between turns.
- Consultative price checks ("Is $45 fair for a base set Mewtwo?").
- The data pipeline end to end on the 28 synthetic raw listings, with fake Apify and TCGdex clients in the tests.
- Offline stand-ins for every LLM call, so everything runs with no keys (`AGENTIC_LLM=offline`).

**Not run for real yet:**

- No live Gemini, Apify or TCGdex call has run from this repo yet. Keys go in `.env`. Next step: notebook 02 with `LIVE = True`, `SCRAPE = True`, `TEST_RUN = True` (5 listings).
- Apify output field names come from the actor's docs. If the first scrape returns different names, adjust `anonymize()` in notebook 02.

**Not built yet:**

- Voice loop: push-to-talk, Whisper, filler line, Edge-TTS (`cli_voice.py` in the plan; `.vscode/launch.json` still points at it).
- Text CLI (`cli_text.py`); for now the chat loop at the end of notebook 07 does this.
- Evaluation: ablation runner, single-agent baseline, LLM judge, statistics (`eval/schema.py` has the results columns).
- 30 traps and 30 decoys with a dev/test split, 50 queries with the answer key.
- Red-flag knowledge base grown from 10 to 30–40 entries with source links.

**Known limits:**

- Sample prices are illustrative placeholders, not market data. Replies say so.
- Market prices are for ungraded single cards only. Graded cards, lots and non-English printings are out of scope.

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
- Hand-written Python: only `src/nbexport.py`, the `__init__.py` files, `eval/schema.py` and the tests.

### One buyer turn (the graph in notebook 07)

```
INTENT      Consumer  LLM reads the request; memory fills budget/persona/condition it didn't state
  │ route_after_intent (Platform): card missing, budget missing, or several printings → CLARIFY
CLARIFY     Platform  code decides, LLM words one question; the graph pauses for the answer
SEARCHING   Merchant  fuzzy match on name, set, variant, min condition (relaxed on the retry)
EVALUATING  Merchant  risk = 1 − (1 − r_price)(1 − r_text)(1 − r_info); one LLM call explains
  │                   the flagged listings; price-check facts for consultative questions
  │ route_after_evaluating (Platform): nothing below the 0.6 gate → SEARCHING once, relaxed
RANKING     Consumer  landed cost → policy (budget, risk, reflection gate) → persona utility
RESPONDING  Humanizer facts with pre-formatted amounts → LLM reply → number check
  │ route_after_responding (Platform): check failed → RESPONDING once more, then the template
DONE        Consumer  save profile and query to SQLite
```

`ChatSession` (notebook 07) runs a conversation: it resends the original request with the clarify answer, and puts the AI disclosure on the first reply of the session.

### Where listings come from

- **Samples** (default, `data.use_samples: true`): `data/samples/sample_listings.json` and `sample_prices.json`.
- **Snapshot**: notebook 02 scrapes Marketplace (Apify), anonymizes, identifies cards (20 per LLM call), filters the scope, fetches TCGdex prices, and writes `data/listings.json`, `data/prices.json` and `data/listings_review.csv` for the hand check. Then set `data.use_samples: false`.
- **Live search** (`merchant.live: true`): the Merchant also scrapes Marketplace for each new card search and appends to `data/live_listings.json`. Only on top of the snapshot, never the samples.

### Switches

| Where | Switch | Effect |
|---|---|---|
| each notebook's setup cell | `LIVE` | `True` = Gemini with your keys; `False` = offline stand-ins |
| notebook 02 | `SCRAPE`, `TEST_RUN` | run Apify (costs credit); 5 listings instead of 100 |
| environment | `AGENTIC_LLM=offline` (or `primary`, `small`, ...) | overrides `llm.active` for everything; the tests set `offline` |
| environment | `NB_NO_EXPORT=1` | running a notebook doesn't rewrite `src/` (the tests set it) |
| `config.yaml` | `llm.active`, `llm.fallback` | model for all agents; model used when the quota runs out |
| `config.yaml` | `data.use_samples` | samples vs the real snapshot |
| `config.yaml` | `merchant.live` | live Marketplace search per request |
| `config.yaml` | `rag.enabled` | Chroma retrieval for flag explanations (keywords always run) |

### Commands

```bash
uv sync                              # Python 3.14 + everything (incl. ipykernel and nbmake)
uv run pytest                        # all tests offline, incl. running every notebook
uv run python -m src.nbexport        # export all notebooks to src/
uv run python -m src.nbexport --check   # exit 1 if a module is stale
uv run ruff check . && uv run ruff format --check .   # what CI runs, notebooks included
```

## Project structure

```
Agentic-Commerce/
├── BUILD_LOG.md, README.md
├── config.yaml                 # every model id, threshold and weight
├── pyproject.toml, uv.lock     # pinned dependencies (uv)
├── .env.example                # key names; your keys go in .env (gitignored)
├── notebooks/                  # THE SOURCE: one notebook per agent
│   ├── 00_foundation.ipynb     # → src/config.py, schemas.py, state.py, memory.py, llm.py
│   ├── 01_tools.ipynb          # → src/tools/*.py
│   ├── 02_data_pipeline.ipynb  # → src/pipeline.py
│   ├── 03_consumer_agent.ipynb # → src/agents/consumer.py
│   ├── 04_merchant_agent.ipynb # → src/agents/merchant.py
│   ├── 05_humanizer_agent.ipynb# → src/agents/humanizer.py
│   ├── 06_platform_agent.ipynb # → src/agents/platform.py
│   └── 07_orchestration.ipynb  # → src/graph.py
├── src/                        # generated from the notebooks (plus nbexport.py, __init__.py)
│   ├── agents/  tools/
├── data/
│   ├── red_flags.md            # red-flag knowledge base
│   ├── samples/                # synthetic listings, prices, raw items, queries
│   └── raw/                    # Apify output (gitignored)
├── eval/schema.py              # results.csv columns
├── docs/decisions.md           # one line per decision
├── tests/                      # pytest, all offline
├── .github/workflows/ci.yml    # ruff + pytest on pull requests
└── .vscode/                    # shared settings and launch configs
```

## What each file does

### Notebooks (edit these)

| File | Purpose |
|---|---|
| `notebooks/00_foundation.ipynb` | Config loader and repo root, the shared schemas, the graph state, SQLite memory, and the LLM client (Gemini/Groq, cache, 429 retries, free-tier fallback, offline handlers). |
| `notebooks/01_tools.ipynb` | Deterministic tools: landed cost, utility, policy rules, market-price lookups, risk score and red-flag matching. Demo tables of risk on the samples. |
| `notebooks/02_data_pipeline.ipynb` | Scrape → anonymize → identify → scope filter → TCGdex prices → `data/listings.json`. Dry run on the samples by default. |
| `notebooks/03_consumer_agent.ipynb` | INTENT, RANKING and DONE nodes; intent parsing and memory backfill. |
| `notebooks/04_merchant_agent.ipynb` | SEARCHING and EVALUATING nodes; search filters, Chroma red-flag retrieval, flag explanations, price check, live search. |
| `notebooks/05_humanizer_agent.ipynb` | RESPONDING node; facts, number check, retry with the error, template fallback. |
| `notebooks/06_platform_agent.ipynb` | CLARIFY node (incl. the printing question) and the three routers. |
| `notebooks/07_orchestration.ipynb` | `build_graph`, `ChatSession`, every sample query end to end, timings, chat loop. |

### Python package (`src/`, generated unless noted)

| File | Purpose |
|---|---|
| `src/__init__.py` | Package marker (hand-written). |
| `src/nbexport.py` | Hand-written. Writes `#| export` cells to modules; `--check` reports stale ones. |
| `src/config.py` | `load_config()`, `ROOT`, `repo_path()`, `env()` (reads `.env` once). |
| `src/schemas.py` | `CardListing`, `ParsedQuery`, `LandedCostResult`, `EvaluatedListing`, condition order and words. |
| `src/state.py` | `AgentState`, the typed state every node reads and writes. |
| `src/memory.py` | `BuyerMemory`: buyer profile and query history in SQLite. |
| `src/llm.py` | `LLM`, `make_llm()`, `offline_handler`, `LLMError`. |
| `src/pipeline.py` | `MarketplaceScraper`, `anonymize`, `extract_cards`, `apply_scope_filter`, `TCGdex`, `resolve_set`, `PriceBook`, `run_ingest`, `load_data`, offline extraction. |
| `src/graph.py` | `build_graph()`, `ChatSession`, `export_architecture_diagram()`. |
| `src/agents/__init__.py` | Package marker (hand-written). |
| `src/agents/consumer.py` | `make_intent_node`, `apply_memory`, `make_ranking_node`, `make_done_node`. |
| `src/agents/merchant.py` | `find`, `distinct_printings`, `RedFlagIndex`, `explain_flags`, `price_check_facts`, `live_refresh`, `make_searching_node`, `make_evaluating_node`. |
| `src/agents/humanizer.py` | `build_facts`, `number_check`, `template_reply`, `make_responding_node`. |
| `src/agents/platform.py` | `needs_clarification`, `make_clarify_node`, `route_after_intent`, `route_after_evaluating`, `route_after_responding`. |
| `src/tools/__init__.py` | Re-exports Pablo's tool functions (hand-written). |
| `src/tools/landed_cost.py` | `compute_landed_cost()`. |
| `src/tools/utility.py` | `compute_utility()`, `rank_listings()` (budget optional). |
| `src/tools/policy.py` | `evaluate_policy()` and the two execution-order guards. |
| `src/tools/prices.py` | `pick_variant_price`, `market_price`, `condition_adjusted`, `find_printing`. |
| `src/tools/risk.py` | `parse_red_flags`, `match_flags`, `assess` → `RiskResult`. |

### Tests (`tests/`, all offline)

| File | Purpose |
|---|---|
| `tests/__init__.py` | Package marker. |
| `tests/conftest.py` | Sets `AGENTIC_LLM=offline`; fixtures for config, sample data, LLM, memory, queries. |
| `tests/test_landed_cost.py` | Pablo's: shipping rules and tax. |
| `tests/test_utility.py` | Pablo's: utility formula and persona ranking. |
| `tests/test_policy.py` | Pablo's: budget and risk rejection, closest rejected, order guards. |
| `tests/test_memory.py` | Pablo's: profile upsert and history. |
| `tests/test_orchestrator_consumer.py` | Pablo's: routers and an end-to-end graph with fakes. |
| `tests/test_platform_consumer_fixes.py` | Regression tests for the persona, consultative and printing-question bugs. |
| `tests/test_pipeline_offline.py` | Anonymization, extraction, scope, set resolution, scraper input and Run object, `run_ingest`. |
| `tests/test_merchant.py` | Search filters, red flags, risk on traps and decoys, nodes, ablation 3, price check. |
| `tests/test_humanizer.py` | Number check, retry with the error, template fallback, budget-gap wording. |
| `tests/test_graph_offline.py` | Every sample query, clarify turn, memory across turns, price check, AI disclosure. |
| `tests/test_llm.py` | Model routing, quota fallback, and that every structured-output schema converts for Gemini. |
| `tests/test_notebooks.py` | Modules match notebooks; every notebook runs offline. |
| `tests/test_build_log.py` | Every file is listed in this log. |

### Config and data

| File | Purpose |
|---|---|
| `config.yaml` | Models, LLM settings, pricing, thresholds, condition multipliers and scores, persona weights, limits, data paths, scrape, TCGdex, search, merchant, RAG, response. |
| `pyproject.toml` | Dependencies, dev tools (pytest, ruff, pre-commit, ipykernel, nbmake), ruff settings. |
| `uv.lock` | Exact versions for both machines. |
| `.env.example` | Key names: `GEMINI_API_KEY`, `GROQ_API_KEY`, `APIFY_API_TOKEN`. |
| `.gitignore` | Keeps `.env`, caches, SQLite files, raw scrapes, `.DS_Store` out of git. |
| `data/red_flags.md` | 10 red-flag entries (severity, patterns, why, source). |
| `data/samples/sample_listings.json` | 24 synthetic in-scope listings: 11 clean, 7 traps, 6 decoys. |
| `data/samples/sample_prices.json` | Illustrative prices for the 8 sample printings (not market data). |
| `data/samples/sample_raw_listings.json` | 28 raw Apify-shaped items for the pipeline dry run (incl. graded, lots, Japanese). |
| `data/samples/sample_queries.json` | 10 queries with expected outcome, acceptable picks and a scripted clarify answer. |

### Docs, eval and setup

| File | Purpose |
|---|---|
| `README.md` | Overview, setup, notebook order. |
| `BUILD_LOG.md` | This file. |
| `docs/decisions.md` | One line per decision, with the reason. |
| `eval/schema.py` | Pablo's: columns of `results.csv` for the evaluation runs. |
| `.github/workflows/ci.yml` | Pablo's CI: `uv sync`, ruff check, ruff format check, pytest (which runs the notebooks). |
| `.vscode/settings.json` | Pablo's: `.venv` interpreter, pytest, ruff on save. |
| `.vscode/launch.json` | Pablo's: launch configs for the planned `cli_text.py`, `cli_voice.py`, `eval/run_ablation.py` (not built yet). |
| `.pre-commit-config.yaml` | Pablo's: ruff and pytest before each commit. |

## Change log

Newest first.

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

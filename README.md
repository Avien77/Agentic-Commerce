# Voice-Driven Multi-Agent Commerce for Pokémon Trading Cards

A local, voice-to-voice multi-agent system built with **LangGraph** and **Python 3.12** that
helps buyers evaluate peer-to-peer Pokémon TCG listings on Facebook Marketplace. It
identifies the exact card behind messy listing titles, checks prices against TCGdex market
data, filters out likely scams through external reflection, enforces budget and safety
policies in deterministic Python, and ranks the surviving options with persona-weighted
utility. It runs from VS Code; there is no app or website.

## Architecture

Four agents share one typed state (`src/state.py`) in a 7-state LangGraph workflow:

```text
START -> INTENT -> [CLARIFY (max 1)] -> SEARCHING -> EVALUATING -> RANKING -> RESPONDING -> DONE -> END
                                            ^            |                       |  ^
                                            +---(max 1)--+                       +--+ (max 1 retry, then template)
```

| Agent | States | Notebook |
|---|---|---|
| Consumer | INTENT, RANKING, DONE | `03_consumer_agent` |
| Merchant | SEARCHING, EVALUATING | `04_merchant_agent` |
| Humanizer | RESPONDING | `05_humanizer_agent` |
| Platform | CLARIFY, routing, policy | `06_platform_agent` |

## The code lives in notebooks

Every module in `src/` (except `src/nbexport.py` and the `__init__.py` files) is generated
from a notebook. Edit the notebook, then run its last cell (**Export**). Never edit the
generated `.py` files: the next export overwrites them, and the tests fail if a module is
out of date with its notebook. Full details: [`BUILD_LOG.md`](BUILD_LOG.md).

## Setup

```bash
uv sync                      # Python 3.12 + all dependencies, incl. Jupyter kernel
cp .env.example .env         # then fill in GEMINI_API_KEY, GROQ_API_KEY, APIFY_API_TOKEN
uv run pytest                # everything offline: no keys, no network
```

In VS Code, open a notebook and pick the `.venv` kernel. Run them in order the first time:

| # | Notebook | What it does |
|---|---|---|
| 00 | `00_foundation` | config, schemas, state, memory, the shared LLM client |
| 01 | `01_tools` | landed cost, utility, policy, prices, risk score |
| 02 | `02_data_pipeline` | Apify scrape → anonymize → card identification → TCGdex prices |
| 03–06 | the four agents | each runs on its own against the sample data |
| 07 | `07_orchestration` | the full graph, every sample query, and a chat loop |

Each notebook starts with `LIVE = False`: offline, rule-based stand-ins for every LLM call,
free. Set `LIVE = True` to use Gemini with your keys (responses are cached in `.cache/llm`).
Scraping costs Apify credit and has its own switch (`SCRAPE` in notebook 02).

## Data

Until the real snapshot exists, the agents use `data/samples/` (24 synthetic listings with
traps and decoys, illustrative prices). After notebook 02 has written `data/listings.json`
and the rows are hand-checked, set `data.use_samples: false` in `config.yaml`.

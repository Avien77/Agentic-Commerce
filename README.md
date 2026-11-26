# Voice-Driven Multi-Agent Commerce for Pokémon Trading Cards

A local, voice-to-voice multi-agent system built with **LangGraph** and **Python 3.14** that
helps buyers evaluate peer-to-peer Pokémon TCG listings on Facebook Marketplace. It
identifies the exact card behind messy listing titles, checks prices against TCGdex market
data, filters out likely scams through external reflection, enforces budget and safety
policies in deterministic Python, and ranks the surviving options with persona-weighted
utility. It runs locally from VS Code: a terminal chat, a voice chat and a local web page
that shows the agents at work and the results. Nothing is deployed.

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
uv sync                      # Python 3.14 + all dependencies, incl. Jupyter kernel
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
| 09 | `09_voice` | the voice chat |
| 08 | `08_evaluation` | the benchmark, the ablation runner, judge, statistics, pipeline and voice evaluations |
| 10 | `10_interface` | the local web page: chat, the agents at work, the results |

In VS Code's **Run and Debug** panel (Cmd+Shift+D), "Demo: run sample queries (offline)"
runs all 10 sample queries and prints PASS/FAIL; "Text chat (offline)" lets you chat with it
in the terminal. Same from the terminal: `uv run python -m src --demo --offline`.

To watch it work in the browser: `uv run python -m src --ui` (type in the page, or click the
microphone and talk: the reply is read aloud) or
`uv run python -m src --voice --ui` (talk; the page follows along). Add `--offline` for the
rule-based agents, or `--replay data/raw/<scrape>.json` for the live search on a saved scrape.
The page shows each listing's price and total, the seller's city, distance and listing date,
the card's rarity, its market value and where that value comes from, and why it ranks where it does.

Each notebook starts with `LIVE = False`: offline, rule-based stand-ins for every LLM call,
free. Set `LIVE = True` to use Gemini with your keys (responses are cached in `.cache/llm`).
Scraping costs Apify credit and has its own switch (`SCRAPE` in notebook 02).

## Evaluation

```bash
uv run python -m src.evaluation run --variants all --split dev --model offline   # wiring check, free
uv run python -m src.evaluation run --variants all --split test --repeats 3 --max-cost 25 --label final
uv run python -m src.evaluation judge eval/results/<folder>    # then: stats <folder>
```

The benchmark (`eval/data/`): 100 synthetic listings (40 clean, 30 scams, 30 honest-but-odd),
50 queries and 5 memory scripts with an answer key. 11 variants, from a single-agent baseline
to each component switched off. Details: notebook 08 and [`BUILD_LOG.md`](BUILD_LOG.md).

## Data

Until the real snapshot exists, the agents use `data/samples/` (24 synthetic listings with
traps and decoys, illustrative prices). After notebook 02 has written `data/listings.json`
and the rows are hand-checked, set `data.use_samples: false` in `config.yaml`.

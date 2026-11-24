# Architecture & Experiment Decision Log

Format: `YYYY-MM-DD | Decision | Rationale`

- 2026-11-23 | Initialized Day 1 shared interfaces (`src/state.py`, `src/schemas.py`), `config.yaml`, and deterministic tools (`landed_cost`, `utility`, `policy`) with pytest coverage. | Locks down shared contracts before parallel agent development.
- 2026-11-23 | Tax calculated on item price (`price * tax_rate`), defaulting `tax_rate=0.0` for private local sales. | Keeps landed cost deterministic and configurable via `config.yaml`.
- 2026-11-24 | Code moved into notebooks (`notebooks/00`–`07`, one per agent). `#| export` cells are written to the same `src/...` modules as before by `src/nbexport.py`, so imports and tests are unchanged. | Team decision: notebooks are the source; generated modules keep the graph and pytest working.
- 2026-11-24 | One shared LLM client (`src/llm.py`): disk cache, 429 retries, automatic fallback to `primary_free_tier`, offline mode via `AGENTIC_LLM=offline`. | Free-tier quota; one place for model choice; tests and CI run without keys.
- 2026-11-24 | The intent LLM no longer sees the saved profile; it returns `persona: null` when unstated and code fills gaps from memory (`filled_from_memory`). | A saved persona was overriding a persona the buyer stated in the same message.
- 2026-11-24 | Policy and ranking accept `budget=None` for consultative questions; P is then measured against the most expensive surviving listing. | "Is $40 fair for X?" crashed RANKING.
- 2026-11-24 | CLARIFY also fires when several printings match and no set is named; budget and printing can be asked in one question. | Plan Section 3; the previous rule for this was unreachable.
- 2026-11-24 | `scripts/ingest.py` replaced by `notebooks/02_data_pipeline.ipynb` (`src/pipeline.py`): Apify `startUrls`/`resultsLimit` with a spend cap, hashed stable ids, batched extraction (20 per call), TCGdex set-name resolution, variant-aware prices. `prices.json` entries are flattened to `{name, set_name, variants}`. | The old script could not run against the actor or apify-client 3.x.
- 2026-11-24 | Risk score and price lookups live in `src/tools/risk.py` and `src/tools/prices.py`. Red-flag severity scores and the price-check "fair" ceiling (115%) are in `config.yaml`. | Plan lists risk and prices under `tools/`; no thresholds in code.
- 2026-11-24 | LLM-facing schemas avoid `gt`/`lt` constraints (Gemini's schema subset rejects `exclusiveMinimum`); code validates instead. | Pablo's intent call would have failed on its first live request.
- 2026-11-24 | Frontier model id corrected to `gemini-3.1-pro-preview`. | The id Google publishes.
- 2026-11-24 | The AI disclosure is added by `ChatSession` on the first reply of a session, not by every reply. | Plan Section 6: "at the start of each session".

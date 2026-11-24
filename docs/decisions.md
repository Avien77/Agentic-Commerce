# Architecture & Experiment Decision Log

Format: `YYYY-MM-DD | Decision | Rationale`

- 2026-11-23 | Initialized Day 1 shared interfaces (`src/state.py`, `src/schemas.py`), `config.yaml`, and deterministic tools (`landed_cost`, `utility`, `policy`) with pytest coverage. | Locks down shared contracts before parallel agent development.
- 2026-11-23 | Tax calculated on item price (`price * tax_rate`), defaulting `tax_rate=0.0` for private local sales. | Keeps landed cost deterministic and configurable via `config.yaml`.

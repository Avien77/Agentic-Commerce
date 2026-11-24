# Voice-Driven Multi-Agent Commerce for Pokémon Trading Cards

A local, voice-to-voice multi-agent system built with **LangGraph** and **Python 3.12** that helps buyers evaluate peer-to-peer Pokémon TCG listings (Facebook Marketplace)[cite: 3, 4, 12]. The system identifies the exact card behind messy listing titles, checks prices against market data, filters out likely scams via external reflection, enforces budget and safety policies in deterministic Python, and ranks surviving options using persona-weighted utility scoring[cite: 3, 4].

---

## Architecture

Four specialized agents share a single typed state (`src/state.py`) in a 7-state LangGraph workflow[cite: 4, 6, 15]:

```text
START -> INTENT -> [CLARIFY (max 1)] -> SEARCHING -> EVALUATING -> RANKING -> RESPONDING -> DONE -> END
                                            ^            |                       |  ^
                                            +---(max 1)--+                       +--+ (max 1 retry, then template)

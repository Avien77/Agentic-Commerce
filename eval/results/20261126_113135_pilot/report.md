# Evaluation run 20261126_113135_pilot

Split: dev · repeats: 1 · model override: small

| Variant | Model | Top-1 (95% CI) | Top-3 | Policy violations | Traps recommended | Scam recall | Decoy FPR | Arithmetic errors | Naturalness | Median latency | Cost/query |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | openai/gpt-oss-20b | 58% (0.385-0.769) | 77% | 50% | 50% | 75% | 50% | 0% | 3.9231 | 17.28 s | $0.0003 |

## Top-1 accuracy by query type

| Variant | Category | Queries | Top-1 |
|---|---|---|---|
| full | complex | 11 | 64% |
| full | consultative | 5 | 60% |
| full | memory | 4 | 25% |
| full | simple | 6 | 67% |

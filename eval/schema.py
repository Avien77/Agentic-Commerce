"""Shared results.csv column schema (Section 10 & 12)."""

RESULTS_CSV_COLUMNS = [
    "run_id",
    "query_id",
    "config_id",
    "repeat",
    "model_id",
    "top1_accurate",
    "top3_accurate",
    "correct_refusal",
    "policy_violation",
    "arithmetic_error",
    "scam_recall",
    "scam_fpr",
    "naturalness_score",
    "latency_sec",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "top_pick_id",
    "prompt_hash",
]

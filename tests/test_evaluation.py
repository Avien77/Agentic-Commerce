"""The evaluation (notebook 08) offline: the benchmark and its answer key, the metrics, the
runner with every variant, the judge, the statistics, the pipeline and voice evaluations."""

import csv
import json
import math
from datetime import date
from pathlib import Path

import pytest

from src.benchmark import (
    ORACLE_WEIGHTS,
    QUERY_SPECS,
    benchmark_listings,
    benchmark_prices,
    build_queries,
    build_scripts,
    eligible,
    load_benchmark,
)
from src.config import ROOT
from src.evaluation import (
    Outcome,
    bootstrap_ci,
    estimate,
    judge,
    judge_agreement,
    mcnemar,
    rating_sheet,
    read_rows,
    run,
    score,
    screening,
    spearman,
    summarize,
    variants,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def ev_cfg(cfg):
    cfg["rag"]["enabled"] = False
    return cfg


@pytest.fixture
def bench(ev_cfg):
    return load_benchmark(ev_cfg)


def by_id(bench):
    return {x.listing_id: x for x in bench.data.listings}


# ---------------------------------------------------------------------------- the benchmark
def test_the_committed_benchmark_is_what_the_code_builds(ev_cfg):
    folder = ROOT / ev_cfg["evaluation"]["benchmark_dir"]
    listings = benchmark_listings()
    built = {"pool.json": [x.model_dump() for x in listings], "prices.json": benchmark_prices(),
             "queries.json": build_queries(listings, ev_cfg),
             "memory_scripts.json": build_scripts(listings, ev_cfg)}  # fmt: skip
    for name, obj in built.items():
        on_disk = json.loads((folder / name).read_text(encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(obj)), f"rebuild eval/data/{name}: run `build`"


def test_the_pool_is_balanced_and_ids_say_nothing(bench):
    xs = bench.data.listings
    assert len(xs) == 100
    count = {(lab, split): sum(x.label == lab and x.split == split for x in xs)
             for lab in ("clean", "trap", "decoy") for split in ("dev", "test")}  # fmt: skip
    assert count[("clean", "dev")] == count[("clean", "test")] == 20
    assert sum(v for (lab, _), v in count.items() if lab == "trap") == 30
    assert sum(v for (lab, _), v in count.items() if lab == "decoy") == 30
    assert all(x.listing_id.startswith("EV") and len(x.listing_id) == 5 for x in xs)
    first_ten = [x.label for x in sorted(xs, key=lambda x: x.listing_id)[:10]]
    assert len(set(first_ten)) > 1  # shuffled, not grouped by kind


def test_dates_move_with_today_so_listing_age_stays_the_same(ev_cfg):
    a = load_benchmark(ev_cfg, today=date(2026, 11, 25))
    b = load_benchmark(ev_cfg, today=date(2027, 3, 1))
    x, y = a.data.listings[0], b.data.listings[0]
    assert (date(2027, 3, 1) - date.fromisoformat(y.listed_at)) == (
        date(2026, 11, 25) - date.fromisoformat(x.listed_at)
    )


def test_query_mix_follows_macdf(bench):
    cats = [q["category"] for q in bench.queries]
    assert (cats.count("simple"), cats.count("complex"), cats.count("consultative")) == (15, 25, 10)
    assert {q["split"] for q in bench.queries} == {"dev", "test"}
    assert len(bench.scripts) == 5 and all(len(s["turns"]) == 2 for s in bench.scripts)


def test_the_answer_key_never_accepts_a_trap_or_a_wrong_card(bench, ev_cfg):
    ids = by_id(bench)
    for q in bench.queries + [t for s in bench.scripts for t in s["turns"]]:
        key = q["key"]
        if key["expect"] == "price_check":
            continue
        for i in key["acceptable"]:
            x = ids[i]
            assert x.label != "trap" and eligible(x, q["truth"], ev_cfg), (q["id"], i)
        assert set(key["acceptable"]) <= set(key["valid"])
        assert all(ids[i].label == "trap" for i in key["bait_traps"])
        assert (key["expect"] == "nothing_fits") == (not key["valid"])


def test_the_oracle_puts_condition_first_for_a_collector(bench):
    ids = by_id(bench)
    c01 = next(q for q in bench.queries if q["id"] == "C01")
    assert c01["truth"]["persona"] == "serious_collector"
    assert {ids[i].condition for i in c01["key"]["acceptable"]} == {"NM"}
    assert ORACLE_WEIGHTS["serious_collector"][1] > 0.5


def test_price_checks_carry_the_market_value_and_verdict(bench):
    keys = {q["id"]: q["key"] for q in bench.queries if q["category"] == "consultative"}
    assert keys["P01"] == {"expect": "price_check", "market_for_condition": 357.0,
                           "market_nm": 420.0, "verdict": "fair"}  # fmt: skip
    assert keys["P04"]["verdict"] == "suspiciously low"
    assert keys["P02"]["verdict"] == "on the high side"
    assert "verdict" not in keys["P05"]


def test_every_query_spec_has_a_unique_id():
    ids = [q["id"] for q in QUERY_SPECS]
    assert len(ids) == len(set(ids)) == 50


# ---------------------------------------------------------------------------- metrics
def query(bench, qid):
    return next(q for q in bench.queries if q["id"] == qid)


def test_score_a_right_answer(bench, ev_cfg):
    q = query(bench, "C01")
    out = Outcome(picks=[q["key"]["acceptable"][0]], reply="Your best bet is the Charizard.")
    row = score(q, out, bench.data, ev_cfg)
    assert row["top1_accurate"] == row["top3_accurate"] == 1
    assert row["policy_violation"] == row["trap_recommended"] == row["arithmetic_error"] == 0
    assert row["scam_recall"] == 1.0


def test_score_a_trap_pick_and_an_invented_amount(bench, ev_cfg):
    q = query(bench, "C12")  # nothing fits; a "premium print" trap is the bait
    trap = q["key"]["bait_traps"][0]
    row = score(q, Outcome(picks=[trap], reply="It's $299.99, a steal."), bench.data, ev_cfg)
    assert row["top1_accurate"] == row["correct_refusal"] == 0
    assert row["policy_violation"] == row["trap_recommended"] == 1
    assert row["arithmetic_error"] == 1
    assert row["scam_recall"] == 0.5  # one of the two bait traps picked


def test_score_a_price_check_needs_the_value_and_the_verdict(bench, ev_cfg):
    q = query(bench, "P04")  # $45 for a NM Charizard ex: suspiciously low, market $115.00
    good = score(q, Outcome(reply="$45.00 is suspiciously low; it goes for about $115.00."),
                 bench.data, ev_cfg)  # fmt: skip
    vague = score(q, Outcome(reply="Hmm, about $115.00 usually."), bench.data, ev_cfg)
    assert good["top1_accurate"] == 1 and vague["top1_accurate"] == 0


def test_passing_over_the_only_honest_answer_is_a_false_positive(bench, ev_cfg):
    q = query(bench, "C03")  # only an honest decoy ("custom sleeve") fits
    assert q["key"]["decoy_only"]
    row = score(q, Outcome(picks=[]), bench.data, ev_cfg)
    assert row["scam_fpr"] == 1 and row["decoy_only"] == 1


def test_statistics_helpers():
    lo, hi = bootstrap_ci([1.0] * 8 + [0.0] * 2)
    assert 0.4 <= lo <= 0.8 <= hi <= 1.0
    m = mcnemar({"a": 1, "b": 1, "c": 0, "d": 1}, {"a": 0, "b": 0, "c": 0, "d": 1})
    assert (m["only_baseline_right"], m["only_variant_right"], m["p_value"]) == (2, 0, 0.5)
    assert spearman([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0
    assert math.isnan(bootstrap_ci([])[0])


# ---------------------------------------------------------------------------- the runner
@pytest.fixture
def small_run(ev_cfg, bench, tmp_path):
    def go(variant_ids, **kw):
        return run(ev_cfg, variant_ids, split="dev", repeats=1, label="t", model_override="offline",
                   out_dir=tmp_path / "run", bench=bench, log=lambda _m: None, **kw)  # fmt: skip

    return go


def test_every_variant_runs_and_writes_the_schema(ev_cfg, small_run):
    from eval.schema import RESULTS_CSV_COLUMNS

    folder = small_run(list(variants(ev_cfg)), limit=6)
    rows = read_rows(folder)
    assert list(rows[0])[: len(RESULTS_CSV_COLUMNS)] == RESULTS_CSV_COLUMNS
    assert {r["config_id"] for r in rows} == set(variants(ev_cfg))
    assert not [r for r in rows if r["error"]]
    files = summarize(folder)
    report = files["report"].read_text()
    assert "| single_agent |" in report and "McNemar" in report
    comps = list(csv.DictReader(files["comparisons"].open()))
    assert {c["variant"] for c in comps} == set(variants(ev_cfg)) - {"full"}


def test_memory_scripts_share_memory_only_when_it_is_on(small_run):
    folder = small_run(["full", "no_memory"], categories={"memory"})
    rows = {(r["config_id"], r["query_id"]): r for r in read_rows(folder)}
    assert ("full", "M01b") in rows and rows[("full", "M01b")]["memory_ok"] != ""
    assert rows[("full", "M01b")]["clarify_asked"] == "0"  # the budget came from memory
    assert rows[("no_memory", "M01b")]["clarify_asked"] == "1"  # it had to ask


def test_the_cost_cap_stops_a_run(ev_cfg, small_run, monkeypatch):
    monkeypatch.setattr("src.evaluation.cost_usd", lambda *a, **k: 0.01)
    folder = small_run(["full"], max_cost=0.025)
    assert len(read_rows(folder)) == 3
    assert json.loads((folder / "run.json").read_text())["stopped_at_cost"] >= 0.025


def test_the_single_agent_answers_in_one_call(ev_cfg, small_run):
    folder = small_run(["single_agent"], limit=4, scripts=False)
    rows = read_rows(folder)
    assert all(r["llm_calls"] == "1" for r in rows)
    assert any(r["picks"] for r in rows)


def test_judge_rating_sheet_and_agreement(ev_cfg, small_run, tmp_path):
    from src.evaluation import eval_llm

    folder = small_run(["full"], limit=4, scripts=False)
    judge(folder, ev_cfg, eval_llm(ev_cfg, "offline", 0), log=lambda _m: None)
    assert all(r["naturalness_score"] for r in read_rows(folder))
    sheet = rating_sheet(folder, tmp_path / "ratings.csv", n=4)
    rows = list(csv.DictReader(sheet.open()))
    for r in rows:
        r["rater1_naturalness"], r["rater2_naturalness"] = "4", "5"
    with sheet.open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    agree = judge_agreement(folder, sheet)
    assert agree["rated"] == len(rows) and agree["within_1_point"] >= 0.5


def test_estimate_prices_each_variant_on_its_own_model(ev_cfg, small_run):
    folder = small_run(["full", "single_agent"], limit=2, scripts=False)
    rows = read_rows(folder)
    for r in rows:  # offline calls have no tokens: pretend the pilot measured some
        r["prompt_tokens"], r["completion_tokens"] = "10000", "500"
    with (folder / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    est = {e["variant"]: e for e in estimate(ev_cfg, folder, ["full", "frontier_single"], 60, 3)}
    assert est["full"]["query_runs"] == 180
    assert est["full"]["cost_usd"] == pytest.approx(180 * (10000 * 0.75 + 500 * 3.75) / 1e6, 0.01)
    assert est["frontier_single"]["cost_usd"] > est["full"]["cost_usd"]


def test_screening_shows_the_test_traps_are_harder(ev_cfg, bench):
    s = screening(ev_cfg, bench)
    assert s["dev"]["trap_recall"] > s["test"]["trap_recall"]
    assert s["all"]["clean_rejected"] == 0.0


# ---------------------------------------------------------------------------- pipeline and voice
def test_pipeline_evaluation_on_the_labeled_samples(ev_cfg, llm):
    from src.eval_pipeline import load_labels, score_pipeline, scrape_health

    items = json.loads((ROOT / "data/samples/sample_raw_listings.json").read_text())
    health = scrape_health(items, ev_cfg)
    assert health["items"] == 28 and health["usable"] == 28 and health["duplicates"] == 0
    labels = load_labels(ROOT / "eval/data/sample_raw_labels.csv")
    result = score_pipeline(ev_cfg, items, labels, llm)
    assert result["scope_precision"] == result["scope_recall"] == 1.0
    assert result["field_accuracy"]["card_name"] == 1.0
    assert result["in_scope"] == 24 and len(result["per_listing"]) == 28


def test_pipeline_label_sheet_is_prefilled(ev_cfg, llm, tmp_path):
    from src.eval_pipeline import label_sheet
    from src.pipeline import anonymize, identify_listings

    items = json.loads((ROOT / "data/samples/sample_raw_listings.json").read_text())
    rows = [r for r in (anonymize(i, ev_cfg) for i in items) if r]
    kept, _, _ = identify_listings(ev_cfg, llm, rows, log=lambda *_: None)
    sheet = list(csv.DictReader(label_sheet(items, tmp_path / "s.csv", ev_cfg, kept).open()))
    assert len(sheet) == 28
    s06 = next(r for r in sheet if r["source_id"] == "S06")  # graded: dropped
    assert s06["in_scope"] == "0" and s06["out_reason"]
    s01 = next(r for r in sheet if r["source_id"] == "S01")
    assert s01["in_scope"] == "1" and s01["card_name"] == "Charizard"


def test_word_error_rate_and_entities():
    from src.eval_voice import entity_recall, wer

    assert wer("Base Set Charizard under $400", "base-set Charizard under 400 dollars") == 0.0
    assert wer("Lugia V alt art", "Lugia 5 alt art") == 0.25
    q = {"text": "Base Set Charizard under $400",
         "truth": {"printings": ["charizard_base"], "budget": 400}}  # fmt: skip
    assert entity_recall(q, "Base Set Charizard under $400") == 1.0
    assert entity_recall(q, "base set charzard under 400") == 1.0  # fuzzy card name
    assert entity_recall(q, "a Blastoise under $40") == 0.0


class EchoTranscriber:
    """Hears the request exactly, or drops the card name without the vocabulary."""

    def __init__(self, texts, drop=False):
        self.texts, self.drop = texts, drop

    def transcribe(self, rec):
        text = self.texts[rec.audio]
        return (text.replace("Charizard", "Chasm herd") if self.drop else text), "fake"


def test_speech_to_text_evaluation_without_network(ev_cfg, bench, tmp_path, monkeypatch):
    from src.eval_voice import run_stt

    monkeypatch.setattr("src.eval_voice.repo_path", lambda p: tmp_path / p)
    texts = {q["text"].encode(): q["text"] for q in bench.queries}
    stt = {"vocabulary": EchoTranscriber(texts), "no_vocabulary": EchoTranscriber(texts, True)}
    folder = run_stt(ev_cfg, "dev", ["v1"], limit=3, bench=bench, stt=stt,
                     synth=lambda t: t.encode(), out_dir=tmp_path / "voice", log=lambda _m: None,
                     agents_model="offline")  # fmt: skip
    summary = json.loads((folder / "voice_summary.json").read_text())
    assert summary["vocabulary"]["wer"] == 0.0 and summary["vocabulary"]["same_pick"] == 1.0
    assert summary["no_vocabulary"]["entity_recall"] < 1.0


def test_h5_timing_summary(tmp_path):
    from src.eval_voice import timing_summary

    log = tmp_path / "runs.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"to_transcript_s": 0.5, "to_filler_s": 6.0, "to_answer_s": 9.0, "graph_s": 8, "tts_s": 0.8},
        {"to_transcript_s": 0.7, "to_filler_s": None, "to_answer_s": 4.0, "graph_s": 3, "tts_s": 0.6},
        {"to_transcript_s": 0.6, "to_filler_s": 5.0, "to_answer_s": 10.0, "graph_s": 9, "tts_s": 0.7},
    ]))  # fmt: skip
    s = timing_summary(log)
    assert s["turns"] == 3 and s["turns_with_filler"] == 2
    assert s["to_filler_s"] == 5.5 and s["filler_before_answer_s"] == 4.0


def test_tts_latency_counts_failures(ev_cfg):
    from src.eval_voice import tts_latency

    def synth(text):
        if "fail" in text:
            raise OSError("403")
        return b"ID3"

    s = tts_latency(["Your best bet is $360.00. More here.", "fail now."], ev_cfg, synth)
    assert s["made"] == 1 and s["failures"] == ["OSError: 403"]


def test_python_m_src_evaluation_help():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "src.evaluation", "--help"], cwd=ROOT,
                            capture_output=True, text=True, check=False)  # fmt: skip
    assert result.returncode == 0 and "estimate" in result.stdout


def test_launch_and_docs_name_the_modules():
    text = (ROOT / "BUILD_LOG.md").read_text()
    for name in ("src/benchmark.py", "src/evaluation.py", "src/eval_pipeline.py",
                 "src/eval_voice.py", "notebooks/08_evaluation.ipynb"):  # fmt: skip
        assert name in text
    assert Path(ROOT / "eval/data/sample_raw_labels.csv").exists()

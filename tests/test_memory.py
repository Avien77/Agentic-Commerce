from pathlib import Path

from src.memory import BuyerMemory


def test_memory_save_load_and_preserve_fields(tmp_path: Path):
    mem = BuyerMemory(db_path=tmp_path / "test.sqlite")
    mem.save_profile(
        session_id="u1",
        budget=60.0,
        persona="serious_collector",
        preferred_set="base1",
        preferred_condition="LP",
    )

    prof = mem.get_profile("u1")
    assert prof["budget"] == 60.0
    assert prof["persona"] == "serious_collector"
    assert prof["preferred_sets"] == ["base1"]
    assert prof["preferred_condition"] == "LP"

    # Updating only preferred_set preserves budget & persona
    mem.save_profile(session_id="u1", preferred_set="sv01")
    prof2 = mem.get_profile("u1")
    assert prof2["budget"] == 60.0
    assert prof2["persona"] == "serious_collector"
    assert prof2["preferred_sets"] == ["base1", "sv01"]


def test_memory_query_history(tmp_path: Path):
    mem = BuyerMemory(db_path=tmp_path / "test.sqlite")
    mem.log_query("u1", "Base Set Charizard under $60", {"budget": 60.0}, "fb_0001")
    hist = mem.get_history("u1")
    assert len(hist) == 1
    assert hist[0]["top_pick_id"] == "fb_0001"

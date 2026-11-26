"""The whole graph offline on the sample data: every sample query, the clarify turn, the
price check, memory across turns, and the AI disclosure."""

import pytest

from src.graph import ChatSession, build_graph


@pytest.fixture
def app(cfg, data, llm, memory):
    return build_graph(cfg, memory=memory, llm=llm, data=data)


def test_every_sample_query(app, cfg, queries):
    for q in queries:
        chat = ChatSession(app, q["id"], cfg)
        reply, state = chat.send(q["request"])
        if state["current_state"] == "CLARIFY":
            reply, state = chat.send(q["clarify_answer"])
        assert state["current_state"] == "DONE", q["id"]
        assert state["number_check_passed"], q["id"]
        ranked = state["ranked_listings"]
        if q["expect_status"] == "recommend":
            assert ranked and ranked[0].listing.listing_id in q["acceptable"], q["id"]
        if q["expect_status"] == "nothing_fits":
            assert not ranked and "closest" in reply, q["id"]
        if q["expect_status"] == "price_check":
            assert f"${state['price_check']['market_for_condition']:,.2f}" in reply, q["id"]
        for item in ranked:
            assert item.listing.label != "trap", (q["id"], item.listing.listing_id)


def test_clarify_then_answer(app, cfg):
    chat = ChatSession(app, "c1", cfg)
    question, state = chat.send("Looking for a Charizard")
    assert state["current_state"] == "CLARIFY" and question.startswith("Hi, I'm an AI")
    assert "Base Set" in question and "151" in question
    reply, state = chat.send("The 151 one, up to $120")
    assert state["ranked_listings"][0].listing.listing_id == "S09"
    assert not reply.startswith("Hi, I'm an AI")  # disclosed once per session


def test_budget_is_remembered_between_turns(app, cfg):
    chat = ChatSession(app, "m1", cfg)
    chat.send("Base Set Mewtwo under $50")
    _, state = chat.send("Base Set Zapdos please")
    assert state["parsed_query"].budget == 50.0
    assert "budget" in state["parsed_query"].filled_from_memory
    assert "your saved budget of $50.00" in state["final_response"]


def test_consultative_question_without_budget_does_not_crash(app):
    state = app.invoke({"session_id": "p1", "user_input": "Is $45 fair for a base set Mewtwo?"})
    assert state["current_state"] == "DONE" and "on the high side" in state["final_response"]


def test_no_budget_after_the_one_question_still_answers(app, cfg):
    chat = ChatSession(app, "nb1", cfg)
    _, state = chat.send("Looking for a Charizard")
    assert state["current_state"] == "CLARIFY"
    reply, state = chat.send("The 151 one")  # still no budget: no second question, no crash
    assert state["current_state"] == "DONE" and state["parsed_query"].budget is None
    assert state["ranked_listings"][0].listing.card_name == "Charizard ex" and "$" in reply


def test_terminal_entry_point(monkeypatch, capsys, tmp_path):
    from src.graph import main

    assert main(["--demo", "--offline"]) == 0
    assert "10/10 sample queries passed" in capsys.readouterr().out
    answers = iter(["I'm good!", "Base Set Mewtwo under $50", "yes", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert main(["--offline", "--db", str(tmp_path / "m.sqlite")]) == 0
    out = capsys.readouterr().out
    assert "assistant: Hi! I'm your AI card-shopping assistant. How are you doing today?" in out
    assert "assistant: Glad to hear it! So what cards are we looking for today?" in out
    assert "Okay, so just to confirm: you're looking for a Mewtwo from Base Set" in out
    assert "Your best bet is the Mewtwo" in out

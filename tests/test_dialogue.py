"""The conversation flow (notebooks 06 and 07): greeting and small talk, the request, one
clarifying question, the "just to confirm" read-back, corrections, and price checks."""

import pytest

from src.agents.platform import describe_request, looks_like_request, read_confirmation
from src.graph import ChatSession, build_graph
from src.schemas import ParsedQuery


@pytest.fixture
def chat(cfg, llm, data, memory):
    cfg["dialogue"]["greet"] = cfg["dialogue"]["confirm"] = True
    app = build_graph(cfg, memory=memory, llm=llm, data=data)
    return ChatSession(app, "dialogue-test", cfg, llm=llm)


def test_greeting_small_talk_read_back_then_the_search(chat, cfg):
    d = cfg["dialogue"]
    assert chat.opening() == d["greeting"] and "AI" in d["greeting"]
    reply, state = chat.send("I'm good, thanks!")
    assert state["current_state"] == "SMALLTALK" and reply.endswith(d["ask_request"])
    reply, state = chat.send("Find me a Base Set Charizard under $400, I care about condition")
    assert state["current_state"] == "CONFIRM"
    assert reply == (
        "Okay, so just to confirm: you're looking for a Charizard from Base Set, with a budget "
        "of $400.00, and condition matters most to you. Is that right?"
    )
    reply, state = chat.send("Yep, that's it.")
    assert (
        state["current_state"] == "DONE" and state["ranked_listings"][0].listing.listing_id == "S04"
    )
    assert "INTENT" not in state["stage_timings"]  # the confirmed query went straight to SEARCHING
    assert not reply.startswith("Hi, I'm an AI")  # the greeting already said it


def test_a_reply_to_the_greeting_can_already_be_the_request(chat):
    chat.opening()
    reply, state = chat.send("Good! Looking for a Base Set Mewtwo under $50")
    assert state["current_state"] == "CONFIRM" and "a Mewtwo from Base Set" in reply


def test_a_correction_is_read_back_once_more(chat):
    chat.send("Base Set Charizard under $400")
    reply, state = chat.send("No, make it under $300")
    assert state["current_state"] == "CONFIRM" and "$300.00" in reply
    reply, state = chat.send("yes")
    assert state["current_state"] == "DONE" and state["parsed_query"].budget == 300


def test_a_plain_no_asks_what_to_change_and_the_rounds_are_bounded(chat, cfg):
    chat.send("Base Set Charizard under $400")
    reply, state = chat.send("no")
    assert reply == cfg["dialogue"]["ask_correction"]
    reply, state = chat.send("under $350")
    assert state["current_state"] == "CONFIRM" and "$350.00" in reply  # read back a 2nd time
    reply, state = chat.send("actually under $320")  # max_confirm_rounds = 2: search now
    assert state["current_state"] == "DONE" and state["parsed_query"].budget == 320


def test_a_clarifying_question_comes_before_the_read_back(chat):
    reply, state = chat.send("Looking for a Charizard")
    assert state["current_state"] == "CLARIFY"
    reply, state = chat.send("The 151 one, up to $120")
    assert state["current_state"] == "CONFIRM" and "a Charizard" in reply and "$120.00" in reply
    reply, state = chat.send("yes please")
    assert state["ranked_listings"][0].listing.listing_id in {"S09", "S11"}


def test_price_checks_are_answered_without_a_read_back(chat):
    reply, state = chat.send("Is $45 fair for a lightly played base set Mewtwo?")
    assert state["current_state"] == "DONE" and "$34.00" in reply


def test_without_the_dialogue_the_graph_runs_as_before(cfg, llm, data, memory):
    app = build_graph(cfg, memory=memory, llm=llm, data=data)  # cfg: greet and confirm off
    chat = ChatSession(app, "plain", cfg, llm=llm)
    assert chat.opening() is None
    reply, state = chat.send("Base Set Charizard under $400")
    assert state["current_state"] == "DONE" and reply.startswith("Hi, I'm an AI")


def test_read_back_wording(cfg):
    q = ParsedQuery(card_name="Umbreon VMAX", variant="holo", min_condition="LP", budget=150,
                    excluded_variants=["reverse"], persona="budget_parent")  # fmt: skip
    assert describe_request(q, cfg) == (
        "an Umbreon VMAX, holo, but not reverse holo, in at least lightly played condition, "
        "with a budget of $150.00, and you want the best price"
    )
    saved = ParsedQuery(card_name="Mew", budget=60, persona="serious_collector",
                        filled_from_memory=["budget", "persona"])  # fmt: skip
    assert describe_request(saved, cfg) == "a Mew, with your usual budget of $60.00"
    assert describe_request(ParsedQuery(card_name="Lugia"), cfg).endswith("with no set budget")


def test_reading_the_answer(llm):
    assert read_confirmation(llm, "q", "Yeah, that's right!").confirmed
    no = read_confirmation(llm, "q", "nope")
    assert not no.confirmed and no.correction is None
    fix = read_confirmation(llm, "q", "No, the 151 one")
    assert not fix.confirmed and fix.correction == "the 151 one"
    assert looks_like_request("great, I need a Lugia") and not looks_like_request("not bad!")


def test_the_sample_data_note_is_given_once_per_conversation(cfg, llm, data, memory):
    from src.agents.humanizer import build_facts

    app = build_graph(cfg, memory=memory, llm=llm, data=data)
    chat = ChatSession(app, "notes", cfg, llm=llm)
    _, first = chat.send("Base Set Charizard under $400")
    _, second = chat.send("Base Set Mewtwo under $50")
    note = "these are sample listings and sample prices, not live data"
    assert note in build_facts({**first, "sample_note_said": False}, cfg, sample_data=True)["notes"]
    assert second["sample_note_said"] is True
    assert note not in build_facts(second, cfg, sample_data=True)["notes"]

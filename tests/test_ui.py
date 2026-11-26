"""The web page (notebook 10) offline: the live board, the listing rows, the card details and
the local web server, with no network and no browser."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from src.config import ROOT
from src.graph import ChatSession, build_graph
from src.ui import (
    BrowserChat,
    CardDetails,
    LiveBoard,
    PageVoice,
    card_info,
    results,
    serve,
)
from tests.test_live_search import RAW_FILE, CountingReplay
from tests.test_pipeline_offline import FakeTCGdex

TODAY = date(2026, 11, 25)


class FakeDetails:
    """Stands in for CardDetails: every card is a Rare with a TCGplayer product."""

    def __init__(self):
        self.asked = []

    def get(self, key):
        self.asked.append(key)
        return {"rarity": "Rare Holo", "image": f"https://img/{key}", "tcgplayer_product": 42}


class LinkedReplay(CountingReplay):
    """The sample raw listings, with the listing page link a real scrape has."""

    def search(self, terms, limit, max_charge_usd, **kw):
        items = super().search(terms, limit, max_charge_usd, **kw)
        return [{**i, "itemUrl": f"https://www.facebook.com/marketplace/item/{i['id']}/"}
                for i in items]  # fmt: skip


@pytest.fixture
def ui_cfg(cfg, tmp_path):
    cfg["ui"]["card_cache"] = str(tmp_path / "cards")
    return cfg


def kinds(board):
    return [e["kind"] for e in board.since(0)]


def last(board, kind):
    return [e for e in board.since(0) if e["kind"] == kind][-1]


def test_a_search_shows_each_listing_with_its_market_value_and_seller(ui_cfg, llm, data, memory):
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(ui_cfg, data, FakeDetails(), info={"input": "typed"}, today=TODAY)
    chat = BrowserChat(ChatSession(app, "ui", ui_cfg, llm=llm), board)
    chat.turn("Base Set Charizard under $400")
    k = kinds(board)
    assert k[:3] == ["info", "chat", "turn"] and k[-3:] == ["chat", "results", "turn"]
    tasks = [(e["step"], e["phase"]) for e in board.since(0) if e["kind"] == "task"]
    assert ("SEARCHING", "start") in tasks and ("RESPONDING", "end") in tasks
    res = last(board, "results")
    top = res["listings"][0]
    assert top["rank"] == 1 and top["spoken"] and top["card"]["name"] == "Charizard"
    assert top["card"]["rarity"] == "Rare Holo"
    assert top["market"]["source"].startswith("Sample price")  # never passed off as real
    assert top["market"]["url"] == "https://www.tcgplayer.com/product/42"
    assert top["market"]["for_condition"] <= top["market"]["price"]
    assert top["total"] >= top["price"] and top["score"] is not None
    assert set(top["seller"]) >= {"city", "distance_miles", "listed_at", "public_meetup"}
    assert set(top["score_parts"]) == set(top["weights"]) and top["reasons"]
    spoken = [r["spoken"] for r in res["listings"]]
    assert spoken[: 1 + ui_cfg["response"]["max_alternatives"]] == [True] * 3
    assert res["query"]["card_name"] == "Charizard" and "Charizard" in res["query"]["text"]
    assert res["funnel"]["steps"][0]["label"] == "All sample listings"
    end = last(board, "turn")
    assert end["phase"] == "end" and end["state"] == "DONE" and not board.busy


def test_a_live_search_links_each_listing_and_shows_the_funnel(ui_cfg, llm, data, memory, tmp_path):
    from src.agents.merchant import make_searching_node
    from src.pipeline import PriceBook

    ui_cfg["merchant"]["live"] = True
    ui_cfg["merchant"]["live_listings"] = str(tmp_path / "live_listings.json")
    for key in ("prices", "tcgdex_sets"):
        ui_cfg["data"][key] = str(tmp_path / f"{key}.json")
    node = make_searching_node(data, ui_cfg, live=True, llm=llm, scraper=LinkedReplay(RAW_FILE),
                               pricebook=PriceBook(ui_cfg, {}, client=FakeTCGdex()))  # fmt: skip
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data, searching_node=node)
    board = LiveBoard(ui_cfg, data, FakeDetails(), today=TODAY)
    BrowserChat(ChatSession(app, "ui-live", ui_cfg, llm=llm), board).turn(
        "Base Set Charizard under $400"
    )
    progress = [e for e in board.since(0) if e["kind"] == "progress"]
    assert [e["step"] for e in progress] == ["searching", "scraped", "identified"]
    assert progress[0]["term"] == "pokemon charizard base set" and progress[1]["count"] == 28
    res = last(board, "results")
    assert all(r["url"].startswith("https://www.facebook.com/marketplace/item/")
               for r in res["listings"])  # fmt: skip
    assert res["listings"][0]["market"]["source"] == "TCGplayer market price, via TCGdex"
    steps = {s["label"]: s["count"] for s in res["funnel"]["steps"]}
    assert steps["Scraped from Marketplace"] == 28 and steps["Single cards identified"] > 0
    assert "links" not in res["funnel"]["live"]
    saved = (tmp_path / "live_listings.json").read_text()
    assert "facebook.com" not in saved  # the links stay in memory (Section 14)


def test_card_details_are_fetched_once_and_never_offline(ui_cfg):
    class Client(FakeTCGdex):
        def card(self, set_id, number):
            self.asked.append(f"{set_id}-{number}")
            return {"rarity": "Rare", "image": "https://assets.tcgdex.net/en/base/base1/4",
                    "pricing": {"tcgplayer": {"holofoil": {"marketPrice": 400.0,
                                                           "productId": 42382}}}}  # fmt: skip

    client = Client()
    details = CardDetails(ui_cfg, client=client)
    first = details.get("base1-4")
    assert first == {"rarity": "Rare", "image": "https://assets.tcgdex.net/en/base/base1/4",
                     "illustrator": None, "tcgplayer_product": 42382}  # fmt: skip
    assert details.get("base1-4") == first and client.asked == ["base1-4"]
    assert details.get(None) == {}
    offline = CardDetails(ui_cfg, client=client, offline=True)
    assert offline.get("base1-4") == first  # the cache still works
    assert offline.get("base1-2") == {} and client.asked == ["base1-4"]
    assert card_info({"name": "x"})["tcgplayer_product"] is None


def test_nothing_fits_still_shows_the_search(ui_cfg, llm, data, memory):
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(ui_cfg, data, FakeDetails(), today=TODAY)
    BrowserChat(ChatSession(app, "ui", ui_cfg, llm=llm), board).turn("Base Set Charizard under $5")
    res = last(board, "results")
    assert res["listings"] == [] and res["rejected_total"] > 0
    assert all(r["rejection_reason"] for r in res["rejected"])


def test_results_need_no_card_details(ui_cfg, llm, data, memory):
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    _, state = ChatSession(app, "ui", ui_cfg, llm=llm).send("Base Set Charizard under $400")
    res = results(state, data, ui_cfg, None, TODAY)
    assert res["listings"] and res["listings"][0]["card"].get("rarity") is None
    json.dumps(res, default=str)  # what the server sends


def test_typed_messages_go_one_at_a_time(ui_cfg, llm, data, memory):
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    chat = BrowserChat(ChatSession(app, "ui", ui_cfg, llm=llm), LiveBoard(ui_cfg, data))
    assert chat.submit("   ") == (False, "empty message")
    chat._lock.acquire()
    assert chat.submit("Base Set Charizard") == (False, "still working on the last message")
    chat._lock.release()


def test_a_failed_turn_is_shown_and_the_page_keeps_going(ui_cfg, llm, data):
    class Broken:
        def opening(self):
            return None

        def send(self, text, on_task=None):
            raise RuntimeError("the graph broke")

    board = LiveBoard(ui_cfg, data)
    chat = BrowserChat(Broken(), board)
    chat.turn("hello")
    assert last(board, "error")["text"] == "RuntimeError: the graph broke" and not board.busy


def wait_for(board, kind, n=1, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if sum(e["kind"] == kind for e in board.since(0)) >= n:
            return
        time.sleep(0.05)
    raise AssertionError(f"no {kind} event after {timeout}s: {kinds(board)}")


def test_the_web_server_serves_the_page_the_events_and_the_chat(ui_cfg, llm, data, memory):
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(ui_cfg, data, FakeDetails(), info={"input": "typed"}, today=TODAY)
    chat = BrowserChat(ChatSession(app, "ui", ui_cfg, llm=llm), board)
    page = serve(board, chat, port=0)
    try:
        html = urllib.request.urlopen(page.url, timeout=5).read().decode()
        assert html.lower().startswith("<!doctype html") and "/api/events" in html
        req = urllib.request.Request(page.url + "api/send", method="POST",
                                     data=json.dumps({"text": "Base Set Charizard under $400"}).encode(),
                                     headers={"Content-Type": "application/json"})  # fmt: skip
        assert urllib.request.urlopen(req, timeout=5).status == 202
        wait_for(board, "results")
        wait_for(board, "turn", 2)
        state = json.loads(urllib.request.urlopen(page.url + "api/state", timeout=5).read())
        assert [e["kind"] for e in state["events"]][-1] == "turn" and not state["busy"]

        # the event stream starts after the last event the page already has
        stream = urllib.request.urlopen(
            urllib.request.Request(page.url + "api/events", headers={"Last-Event-ID": "0"}),
            timeout=5,
        )
        lines = [stream.readline().decode().strip() for _ in range(2)]
        assert lines[0] == "id: 1" and json.loads(lines[1][len("data: ") :])["kind"] == "chat"
        stream.close()
    finally:
        page.close()


def test_in_voice_mode_the_page_only_follows_along(ui_cfg, data):
    page = serve(LiveBoard(ui_cfg, data, info={"input": "voice"}), None, port=0)
    try:
        req = urllib.request.Request(page.url + "api/send", method="POST", data=b'{"text":"hi"}')
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5)
        assert err.value.code == 409
    finally:
        page.close()


def test_the_voice_chat_mirrors_to_the_page(ui_cfg, llm, data, memory, tmp_path):
    from src.voice import Voice, VoiceChat
    from tests.test_voice import FakeTranscriber, RecordingSpeaker, spoken, wav_synth

    ui_cfg["voice"]["clip_cache"] = str(tmp_path / "clips")
    app = build_graph(ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(ui_cfg, data, FakeDetails(), today=TODAY)
    vc = VoiceChat(ChatSession(app, "voice-ui", ui_cfg, llm=llm), ui_cfg,
                   FakeTranscriber(["Base Set Charizard under $400"]),
                   Voice(ui_cfg, synth=wav_synth), RecordingSpeaker(),
                   log_path=tmp_path / "runs.jsonl", echo=lambda _line: None, board=board)  # fmt: skip
    row = vc.turn(spoken())
    wait_for(board, "results")
    wait_for(board, "turn", 2)
    chats = [(e["role"], e["text"], e["via"]) for e in board.since(0) if e["kind"] == "chat"]
    assert chats == [("user", "Base Set Charizard under $400", "voice"),
                     ("assistant", row["reply"], "voice")]  # fmt: skip
    notes = [e["text"] for e in board.since(0) if e["kind"] == "note"]
    assert notes == [row["filler"]]  # the filler said while the agents worked


def test_python_m_src_ui_starts_the_web_page():
    result = subprocess.run(
        [sys.executable, "-m", "src", "--ui", "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0 and "--no-browser" in result.stdout


# ---------------------------------------------------------------------------- the microphone
class HeardTranscriber:
    """Stands in for Groq Whisper: hears the next text, or fails."""

    def __init__(self, *texts):
        self.texts, self.files = list(texts), []

    def transcribe(self, rec):
        self.files.append(rec.filename)
        text = self.texts.pop(0)
        if isinstance(text, Exception):
            raise text
        return text, "fake"


class FakeSynth:
    def __init__(self, fail=False):
        self.said, self.fail = [], fail

    def __call__(self, text):
        self.said.append(text)
        if self.fail:
            raise OSError("403 from Edge-TTS")
        return b"ID3" + text.encode()


@pytest.fixture
def voice_ui_cfg(ui_cfg, tmp_path):
    ui_cfg["voice"]["clip_cache"] = str(tmp_path / "clips")
    return ui_cfg


def post_audio(page, audio=b"webm-bytes", seconds="1.5", kind="audio/webm;codecs=opus"):
    req = urllib.request.Request(page.url + "api/voice", method="POST", data=audio,
                                 headers={"Content-Type": kind, "X-Seconds": seconds})  # fmt: skip
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_spoken_message_is_transcribed_narrated_and_read_aloud(voice_ui_cfg, llm, data, memory):
    from src.voice import sentences, speakable

    app = build_graph(voice_ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(voice_ui_cfg, data, FakeDetails(), today=TODAY)
    heard = HeardTranscriber("Base Set Charizard under $400")
    voice = PageVoice(voice_ui_cfg, transcriber=heard, synth=FakeSynth())
    chat = BrowserChat(ChatSession(app, "mic", voice_ui_cfg, llm=llm), board, voice)
    page = serve(board, chat, port=0)
    try:
        assert post_audio(page) == (202, {"ok": True, "detail": "ok"})
        wait_for(board, "results")
        wait_for(board, "turn", 2)
    finally:
        page.close()
    assert heard.files == ["speech.webm"]
    events = board.since(0)
    assert [e["kind"] for e in events][1:3] == ["status", "chat"]
    user = events[2]
    assert (user["role"], user["text"], user["via"]) == ("user", "Base Set Charizard under $400",
                                                          "voice")  # fmt: skip
    notes = [e for e in events if e["kind"] == "note"]
    assert [(n["line"], n["say"]) for n in notes] == [("filler", True)]
    assert notes[0]["text"] == voice_ui_cfg["voice"]["fillers"][0]
    reply = [e for e in events if e["kind"] == "chat" and e["role"] == "assistant"][-1]
    assert reply["say"] == sentences(speakable(reply["text"])) and "$360.00" not in reply["say"][0]


def test_the_microphone_refuses_what_it_cant_use(voice_ui_cfg, llm, data, memory):
    app = build_graph(voice_ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(voice_ui_cfg, data, FakeDetails(), today=TODAY)
    heard = HeardTranscriber(RuntimeError("groq: 401"), "Base Set Mewtwo under $50")
    voice = PageVoice(voice_ui_cfg, transcriber=heard, synth=FakeSynth())
    chat = BrowserChat(ChatSession(app, "mic", voice_ui_cfg, llm=llm), board, voice)
    typed_only = BrowserChat(ChatSession(app, "typed", voice_ui_cfg, llm=llm), board)
    assert typed_only.submit_audio(b"x", "audio/webm", 2.0) == (False, "the microphone is off")
    assert chat.submit_audio(b"x", "audio/webm", 0.1)[1].startswith("too short")
    chat.spoken(b"x", "audio/mp4")  # transcription failed: said on the page, nothing else
    assert last(board, "error")["text"].startswith("Couldn't make out what you said (groq: 401)")
    assert heard.files == ["speech.mp4"] and not board.busy
    assert chat.submit_audio(b"x", "audio/ogg", 2.0) == (True, "ok")  # the next one works
    wait_for(board, "results")


def test_each_line_is_read_in_the_voice_chats_voice(voice_ui_cfg, llm, data, memory):
    app = build_graph(voice_ui_cfg, memory=memory, llm=llm, data=data)
    board = LiveBoard(voice_ui_cfg, data)
    synth = FakeSynth()
    voice = PageVoice(voice_ui_cfg, transcriber=HeardTranscriber(), synth=synth)
    page = serve(board, BrowserChat(ChatSession(app, "s", voice_ui_cfg, llm=llm), board, voice),
                 port=0)  # fmt: skip
    try:
        r = urllib.request.urlopen(page.url + "api/speech?text=" + urllib.parse.quote(
            "Your best bet is the Charizard 4/102 for $360.00."), timeout=5)  # fmt: skip
        assert r.headers["Content-Type"] == "audio/mpeg"
        assert r.read() == b"ID3Your best bet is the Charizard 4 of 102 for $360."
        line = voice_ui_cfg["voice"]["search_lines"][0]
        for _ in range(2):  # a fixed line is made once, then read from voice.clip_cache
            urllib.request.urlopen(page.url + "api/speech?fixed=1&text=" + urllib.parse.quote(line),
                                   timeout=5).read()  # fmt: skip
        assert synth.said.count(line) == 1
        assert list(Path(voice_ui_cfg["voice"]["clip_cache"]).glob("*.mp3"))
        synth.fail = True
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(page.url + "api/speech?text=hello", timeout=5)
        assert err.value.code == 503  # the page then uses the browser's own voice
    finally:
        page.close()


def test_warm_up_makes_every_fixed_line_once(voice_ui_cfg):
    synth = FakeSynth()
    voice = PageVoice(voice_ui_cfg, transcriber=HeardTranscriber(), synth=synth)
    voice.warm_up().join(timeout=5)
    assert sorted(synth.said) == sorted(set(voice.fixed))
    voice.warm_up().join(timeout=5)
    assert len(synth.said) == len(set(voice.fixed))  # all from the cache now


def test_a_spoken_live_search_gets_the_search_lines(voice_ui_cfg, llm, data, memory, tmp_path):
    from src.agents.merchant import make_searching_node
    from src.pipeline import PriceBook

    v = voice_ui_cfg["voice"]
    v["still_after_s"] = 0.5
    voice_ui_cfg["merchant"]["live_listings"] = str(tmp_path / "live.json")
    for key in ("prices", "tcgdex_sets"):
        voice_ui_cfg["data"][key] = str(tmp_path / f"{key}.json")
    node = make_searching_node(data, voice_ui_cfg, live=True, llm=llm,
                               scraper=LinkedReplay(RAW_FILE, delay=1.5),
                               pricebook=PriceBook(voice_ui_cfg, {}, client=FakeTCGdex()))  # fmt: skip
    app = build_graph(voice_ui_cfg, memory=memory, llm=llm, data=data, searching_node=node)
    board = LiveBoard(voice_ui_cfg, data, FakeDetails(), today=TODAY)
    voice = PageVoice(voice_ui_cfg, transcriber=HeardTranscriber(), synth=FakeSynth())
    chat = BrowserChat(ChatSession(app, "live-mic", voice_ui_cfg, llm=llm), board, voice)
    chat.turn("Base Set Charizard under $400", via="voice")
    said = [(e["line"], e["text"]) for e in board.since(0) if e["kind"] == "note"]
    kinds = [k for k, _ in said]
    assert said[0] == ("search", v["search_lines"][0])
    assert "still" in kinds and kinds.index("still") < kinds.index("progress")
    assert [t for k, t in said if k == "progress"] == [v["progress_lines"]["scraped"],
                                                      v["progress_lines"]["identified"]]  # fmt: skip
    assert kinds[-1] == "filler"
    assert last(board, "chat")["say"]  # the reply, to read aloud

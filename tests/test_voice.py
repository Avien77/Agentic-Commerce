"""The voice chat (notebook 09) offline: fake speech services, no audio device, no network."""

import asyncio
import copy
import io
import json
import subprocess
import sys
import time
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from src.config import ROOT, load_config
from src.graph import ChatSession, build_graph
from src.voice import (
    MIC_HINT,
    Recording,
    Speaker,
    Transcriber,
    TranscriptionError,
    Voice,
    VoiceChat,
    sentences,
    speakable,
    vocabulary_prompt,
    wav_bytes,
)


def tone(seconds=0.3, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    return (8000 * np.sin(2 * np.pi * 440 * t)).astype("int16")


def spoken():
    """A loud enough, long enough microphone recording that just ended."""
    return Recording(wav_bytes(tone(), 16000), "speech.wav", time.perf_counter(), 0.6, 0.25)


def wav_synth(text):  # stands in for Edge-TTS: WAV instead of MP3, decoded by the same code
    return wav_bytes(tone(0.2, 24000), 24000)


class FakeTranscriber:
    def __init__(self, texts):
        self.texts = list(texts)

    def transcribe(self, rec):
        return self.texts.pop(0), "fake"


class RecordingSpeaker(Speaker):
    """Remembers what it was asked to play and plays nothing."""

    def __init__(self):
        super().__init__(mute=True)
        self.played = []

    def play(self, clip):
        self.played.append(clip.text)
        return super().play(clip)


@pytest.fixture
def voice_cfg(cfg, tmp_path):
    cfg["voice"]["clip_cache"] = str(tmp_path / "clips")
    return cfg


@pytest.fixture
def make_chat(voice_cfg, llm, data, memory, tmp_path):
    def make(texts):
        app = build_graph(voice_cfg, memory=memory, llm=llm, data=data)
        speaker = RecordingSpeaker()
        vc = VoiceChat(
            ChatSession(app, "voice-test", voice_cfg),
            voice_cfg,
            FakeTranscriber(texts),
            Voice(voice_cfg, synth=wav_synth),
            speaker,
            log_path=tmp_path / "runs.jsonl",
            model="rules",
            echo=lambda _line: None,
        )
        return vc, speaker

    return make


def test_microphone_audio_is_16khz_mono_wav():
    with wave.open(io.BytesIO(wav_bytes(tone(), 16000))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (
            1, 2, 16000, 4800
        )  # fmt: skip


def test_speech_reads_prices_and_card_numbers_naturally():
    assert speakable("the Charizard 4/102 for $360.00 total, $40.50 over") == (
        "the Charizard 4 of 102 for $360 total, $40.50 over"
    )
    assert speakable("$1,001.00 and 52%") == "$1,001 and 52%"


def test_replies_are_spoken_sentence_by_sentence():
    reply = (
        "Hi, I'm an AI shopping assistant. The Charizard is $360 total. Is that OK? $45 is high."
    )
    assert sentences(reply) == [
        "Hi, I'm an AI shopping assistant.",
        "The Charizard is $360 total.",
        "Is that OK?",
        "$45 is high.",
    ]
    assert sentences("It's $40.50 over, about 1.5x the price.") == [
        "It's $40.50 over, about 1.5x the price."
    ]


def test_transcriber_uses_groq_then_gemini_then_gives_up(cfg):
    sent = {}

    def groq_ok(**kw):
        sent.update(kw)
        return SimpleNamespace(text=" Base Set Mewtwo under $50 ")

    def groq_down(**kw):
        raise RuntimeError("groq down")

    def groq(create):
        return SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))

    models_used = []

    def gemini(text):
        def generate_content(model, contents, config):
            models_used.append(model)
            return SimpleNamespace(text=text)

        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

    rec = spoken()
    t = Transcriber(cfg, groq=groq(groq_ok), gemini=gemini("unused"))
    assert t.transcribe(rec) == ("Base Set Mewtwo under $50", "groq")
    assert sent["model"] == cfg["models"]["stt"] and sent["file"] == ("speech.wav", rec.audio)
    assert sent["prompt"].startswith("Pokémon cards: ") and "Mewtwo" in sent["prompt"]
    assert models_used == []

    t = Transcriber(cfg, groq=groq(groq_down), gemini=gemini("Pikachu VMAX under $15"))
    assert t.transcribe(rec) == ("Pikachu VMAX under $15", "gemini")
    assert models_used == [cfg["models"]["stt_fallback"]]

    with pytest.raises(TranscriptionError, match="groq down.*empty transcript"):
        Transcriber(cfg, groq=groq(groq_down), gemini=gemini("")).transcribe(rec)


def test_vocabulary_prompt_lists_each_name_once_within_the_limit():
    assert vocabulary_prompt(["Mewtwo", "Base Set", "mewtwo", ""], 100) == (
        "Pokémon cards: Mewtwo, Base Set"
    )
    long = vocabulary_prompt([f"Card {i}" for i in range(100)], 60)
    assert len(long) <= 61 and long.endswith(".") and ", Card 1," in long


def test_edge_tts_limit_is_on_silence_not_on_the_whole_reply(voice_cfg, monkeypatch):
    import edge_tts

    def fake_communicate(gap):
        class Communicate:
            def __init__(self, text, voice, rate):
                pass

            async def stream(self):
                for _ in range(3):
                    await asyncio.sleep(gap)
                    yield {"type": "audio", "data": b"mp3"}

        return Communicate

    voice_cfg["limits"]["tts_timeout_seconds"] = 0.2
    monkeypatch.setattr(edge_tts, "Communicate", fake_communicate(0.1))
    assert Voice(voice_cfg).edge_tts("a long reply") == b"mp3mp3mp3"  # 0.3 s in all
    monkeypatch.setattr(edge_tts, "Communicate", fake_communicate(0.5))
    with pytest.raises(TimeoutError):
        Voice(voice_cfg).edge_tts("Edge-TTS stalls")


def test_voice_falls_back_to_the_local_voice_and_caches_fillers(voice_cfg):
    clip = Voice(voice_cfg, synth=wav_synth).clip("hello")
    assert clip.source == "edge-tts" and clip.rate == 24000 and clip.samples.dtype == np.float32

    def slow(text):
        raise TimeoutError

    v = Voice(voice_cfg, synth=slow)
    clip = v.clip("hello")
    assert clip.source == v.fallback and clip.samples is None and v.last_error == "TimeoutError"

    calls = []

    def counting(text):
        calls.append(text)
        return wav_synth(text)

    v = Voice(voice_cfg, synth=counting)
    assert v.clip("one moment", cache=True).source == "edge-tts"
    assert v.clip("one moment", cache=True).source == "edge-tts"
    assert calls == ["one moment"]  # the second one came from the clip cache


def test_filler_starts_with_evaluating_and_the_answer_follows(make_chat, voice_cfg, tmp_path):
    vc, speaker = make_chat(["Base Set Charizard under $400, I care about condition"])
    row = vc.turn(spoken())
    assert row["state"] == "DONE" and (row["stt"], row["tts"]) == ("fake", "edge-tts")
    assert speaker.played == [voice_cfg["voice"]["fillers"][0], *sentences(speakable(row["reply"]))]
    assert row["filler"] == speaker.played[0]
    assert 0 <= row["to_transcript_s"] <= row["to_filler_s"] <= row["to_answer_s"]
    assert set(row["stages"]) == {"INTENT", "SEARCHING", "EVALUATING", "RANKING", "RESPONDING",
                                  "DONE"}  # fmt: skip
    logged = [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert logged == [row]


def test_a_clarifying_question_gets_no_filler(make_chat, voice_cfg, queries):
    q03 = next(q for q in queries if q["id"] == "Q03")
    vc, speaker = make_chat([q03["request"], q03["clarify_answer"]])
    asked = vc.turn(spoken())
    assert asked["state"] == "CLARIFY" and asked["filler"] is None and asked["to_filler_s"] is None
    assert "EVALUATING" not in asked["stages"]
    assert speaker.played == sentences(speakable(asked["reply"]))
    answered = vc.turn(spoken())
    assert answered["state"] == "DONE" and answered["filler"] == voice_cfg["voice"]["fillers"][0]


def test_silent_or_too_short_recordings_are_not_sent(make_chat, tmp_path):
    lines = []
    vc, speaker = make_chat(["never used"])
    vc.echo = lines.append
    assert vc.turn(Recording(b"...", "speech.wav", 0.0, seconds=2.0, peak=0.0)) is None
    assert vc.turn(Recording(b"...", "speech.wav", 0.0, seconds=0.1, peak=0.4)) is None
    assert lines[0] == MIC_HINT and "too short" in lines[1]
    assert speaker.played == [] and not (tmp_path / "runs.jsonl").exists()


def test_streamed_turns_match_plain_turns(cfg, llm, data, memory, queries):
    app = build_graph(cfg, memory=memory, llm=llm, data=data)
    for q in queries:
        events = []
        plain, _ = ChatSession(app, q["id"], cfg).send(q["request"])
        streamed, _ = ChatSession(app, q["id"] + "-streamed", cfg).send(
            q["request"], on_task=lambda name, phase, _info, ev=events: ev.append((name, phase))
        )
        assert streamed == plain, q["id"]
        assert events[0] == ("INTENT", "start")
        starts = [n for n, p in events if p == "start"]
        assert starts == [n for n, p in events if p == "end"]


def test_voice_entry_point_with_typing(monkeypatch, capsys, tmp_path):
    from src.voice import main

    def no_network(self, text):
        raise OSError("no network in tests")

    def isolated_config():  # no filler clips from an earlier run in .cache/voice
        c = copy.deepcopy(load_config())
        c["voice"]["clip_cache"] = str(tmp_path / "clips")
        return c

    monkeypatch.setattr("src.voice.load_config", isolated_config)
    monkeypatch.setattr(Voice, "edge_tts", no_network)
    answers = iter(["I'm good!", "Base Set Mewtwo under $50", "yes", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    log = tmp_path / "runs.jsonl"
    args = ["--voice", "--offline", "--keyboard", "--mute", "--db", str(tmp_path / "m.sqlite")]
    assert main([*args, "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "Edge-TTS failed (OSError: no network in tests)" in out
    assert "assistant: Hi! I'm your AI card-shopping assistant" in out
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["state"] for r in rows] == ["SMALLTALK", "CONFIRM", "DONE"]
    assert rows[-1]["stt"] == "keyboard" and rows[-1]["to_filler_s"] is not None


def test_python_m_src_voice_starts_the_voice_chat():
    result = subprocess.run(
        [sys.executable, "-m", "src", "--voice", "--help"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0 and "--keyboard" in result.stdout


# ---------------------------------------------------------------------------- live search lines
def test_a_live_search_gets_a_search_line_progress_and_still_working_lines(
    voice_cfg, llm, data, memory, tmp_path
):
    from src.agents.merchant import make_searching_node
    from src.pipeline import PriceBook
    from tests.test_live_search import RAW_FILE, CountingReplay
    from tests.test_pipeline_offline import FakeTCGdex

    v = voice_cfg["voice"]
    v["still_after_s"] = 0.5
    voice_cfg["merchant"]["live_listings"] = str(tmp_path / "live.json")
    for key in ("prices", "tcgdex_sets"):
        voice_cfg["data"][key] = str(tmp_path / f"{key}.json")
    node = make_searching_node(data, voice_cfg, live=True, llm=llm,
                               scraper=CountingReplay(RAW_FILE, delay=2.2),
                               pricebook=PriceBook(voice_cfg, {}, client=FakeTCGdex()))  # fmt: skip
    app = build_graph(voice_cfg, memory=memory, llm=llm, data=data, searching_node=node)
    speaker = RecordingSpeaker()
    vc = VoiceChat(ChatSession(app, "live-voice", voice_cfg, llm=llm), voice_cfg,
                   FakeTranscriber([]), Voice(voice_cfg, synth=wav_synth), speaker,
                   log_path=tmp_path / "runs.jsonl", echo=lambda _line: None)  # fmt: skip
    row = vc.turn(typed="Base Set Charizard under $400")
    played = speaker.played
    answer = sentences(speakable(row["reply"]))
    assert played[0] == v["search_lines"][0] and played[-len(answer) :] == answer
    waiting = played[1 : -len(answer)]  # everything said while the agents worked
    lines = v["still_lines"] + list(v["progress_lines"].values()) + [v["fillers"][0]]
    assert set(waiting) <= set(lines)
    # the scrape took 2.2 s with nothing said: a still-working line came before the results
    assert waiting.index(v["still_lines"][0]) < waiting.index(v["progress_lines"]["scraped"])
    assert (waiting.index(v["progress_lines"]["scraped"])
            < waiting.index(v["progress_lines"]["identified"])
            < waiting.index(v["fillers"][0]))  # fmt: skip
    assert row["to_search_line_s"] < row["to_filler_s"] < row["to_answer_s"]
    assert row["live"]["scraped"] == 28 and row["live"]["kept"] > 0


def test_the_greeting_is_spoken_first(voice_cfg, llm, data, memory, tmp_path):
    voice_cfg["dialogue"]["greet"] = True
    app = build_graph(voice_cfg, memory=memory, llm=llm, data=data)
    speaker = RecordingSpeaker()
    vc = VoiceChat(ChatSession(app, "hello", voice_cfg, llm=llm), voice_cfg, FakeTranscriber([]),
                   Voice(voice_cfg, synth=wav_synth), speaker, log_path=tmp_path / "r.jsonl",
                   echo=lambda _line: None)  # fmt: skip
    assert vc.start() == voice_cfg["dialogue"]["greeting"]
    assert speaker.played == sentences(voice_cfg["dialogue"]["greeting"])
    row = vc.turn(typed="Pretty good, thanks")
    assert row["state"] == "SMALLTALK" and row["reply"].endswith("looking for today?")

"""Shared test setup: every test runs offline (rule-based LLM stand-ins, no API calls) on the
sample data, with Chroma retrieval off and caches in a temp folder."""

import copy
import json
import os

import pytest

os.environ["AGENTIC_LLM"] = "offline"  # before any src import builds an LLM

from src.config import ROOT, load_config
from src.llm import make_llm
from src.memory import BuyerMemory
from src.pipeline import load_data


@pytest.fixture
def cfg():
    c = copy.deepcopy(load_config())
    c["data"]["use_samples"] = True
    c["rag"]["enabled"] = False
    c["merchant"]["live"] = False
    c["dialogue"]["greet"] = False  # tests of the new conversation flow turn these back on
    c["dialogue"]["confirm"] = False
    return c


@pytest.fixture
def data(cfg):
    return load_data(cfg)


@pytest.fixture
def llm(cfg):
    return make_llm(cfg, "offline")


@pytest.fixture
def memory(tmp_path):
    return BuyerMemory(db_path=tmp_path / "buyer.sqlite")


@pytest.fixture
def listing(data):
    by_id = {x.listing_id: x for x in data.listings}
    return lambda lid: by_id[lid]


@pytest.fixture
def queries():
    return json.loads((ROOT / "data/samples/sample_queries.json").read_text(encoding="utf-8"))

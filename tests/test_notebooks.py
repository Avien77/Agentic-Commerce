"""The notebooks are the source: the generated modules must match them, and every notebook
must run top to bottom offline (no API keys, no network)."""

import os
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

from src.config import ROOT
from src.nbexport import export_all

NOTEBOOKS = sorted((ROOT / "notebooks").glob("*.ipynb"))


def test_generated_modules_match_notebooks():
    stale = export_all(check=True, quiet=True)
    assert stale == [], f"Run the notebook's export cell: out of date {stale}"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_notebook_runs_offline(path: Path, monkeypatch):
    monkeypatch.setenv("NB_NO_EXPORT", "1")  # running a notebook must not rewrite src/
    monkeypatch.setenv("AGENTIC_LLM", "offline")
    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=180, kernel_name="python3", resources={
        "metadata": {"path": str(path.parent)}
    }).execute()  # fmt: skip
    assert os.environ["NB_NO_EXPORT"] == "1"

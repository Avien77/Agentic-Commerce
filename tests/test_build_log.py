"""BUILD_LOG.md must list every code, config and data file, so no file goes unlogged."""

from src.config import ROOT

PATTERNS = [
    "notebooks/*.ipynb",
    "src/**/*.py",
    "tests/*.py",
    "eval/*.py",
    "data/samples/*.json",
    "data/red_flags.md",
    "config.yaml",
    ".python-version",
    "data/raw/.gitkeep",
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    ".gitignore",
    "README.md",
    "docs/decisions.md",
    ".github/workflows/*.yml",
    ".vscode/*.json",
    ".pre-commit-config.yaml",
]


def test_every_file_is_in_the_build_log():
    log = (ROOT / "BUILD_LOG.md").read_text(encoding="utf-8")
    files = sorted({p.relative_to(ROOT).as_posix() for pat in PATTERNS for p in ROOT.glob(pat)})
    missing = [f for f in files if f"`{f}`" not in log]
    assert not missing, f"Add these to 'What each file does' in BUILD_LOG.md: {missing}"

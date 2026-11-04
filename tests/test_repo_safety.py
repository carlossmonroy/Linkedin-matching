# Security regression tests: they fail if a future change to .gitignore would let a
# secret or personal data reach GitHub.
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IGNORED = {
    line.strip()
    for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


@pytest.mark.parametrize("entry", [
    ".env",                      # API key
    "config/criteria.md",        # personal profile
    "config/cv_base.md",         # CV
    "config/salary_floors.toml", # personal salary floors
    "tests/fixtures/private/",   # real LinkedIn captures
    "evals/golden_set/",         # real labeled postings
    "applications/",             # generated CVs and cover letters
    "PROYECTO_ANALIZADOR_VACANTES.md",   # original design notes with personal context
])
def test_private_files_are_gitignored(entry):
    assert entry in IGNORED


def test_env_example_holds_no_key():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "sk-ant-" not in example

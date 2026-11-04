# Job Analyzer

Local tool that turns job postings copied from LinkedIn into structured job cards with Claude,
filters out the impossible ones and ranks the rest.

It never automates LinkedIn: you browse and copy the page yourself, and the tool only reads
your clipboard or a text file. No scraping, no bots, no auto-apply.

- Design and roadmap: [docs/design.md](docs/design.md).
- Code walkthrough (flow, diagrams, syntax, exercises): [docs/code-walkthrough.md](docs/code-walkthrough.md).

## Status: phase 1 (CLI)

| Module | What it does |
|---|---|
| `job_analyzer/trim.py` | `trim_page()` and `extract_url_info()` (job ID, canonical URL, source search) |
| `job_analyzer/models.py` | `JobPosting` schema for structured output; LinkedIn signals as a closed list |
| `job_analyzer/ranking.py` | `days_since_posted()`, `recency_weight()`, `fit()`, `opportunity()`, `priority()` |
| `job_analyzer/rules.py` | Hard discards (clearance/ITAR, citizenship, local candidates only outside Mexico) and 1–5 score validation |
| `job_analyzer/analyze.py` | Claude call (`claude-sonnet-5-5`) and CLI |
| `config/criteria.example.md` | Template for your profile and the "my field" scale |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
cp .env.example .env                                  # then paste your API key into .env
cp config/criteria.example.md config/criteria.md      # then fill in your profile
uv run pytest
```

## Usage

```bash
uv run python -m job_analyzer.analyze capture.txt --trim-only   # no API call, no cost
uv run python -m job_analyzer.analyze capture.txt               # needs ANTHROPIC_API_KEY in .env
```

## Security and privacy

- **API key**: lives only in `.env`, which is git-ignored. It is loaded into the process at
  run time and never printed. Do not set it as a system-wide environment variable.
- **Personal data stays local**: `config/criteria.md` (your profile), `config/cv_base.md`,
  real LinkedIn captures in `tests/fixtures/private/`, the eval golden set and generated
  applications are git-ignored. Only the `.example` templates and synthetic fixtures are committed.
- `tests/test_repo_safety.py` fails if any of those entries disappears from `.gitignore`.
- If a key is ever committed by mistake, **revoke it in the Claude Console first**; removing it
  from the history does not make it safe again.

"""Analyze one job posting with Claude (structured output).

Usage: python -m job_analyzer.analyze capture.txt [--model claude-haiku-5-5] [--trim-only]

This is the ENTRY POINT of phase 1. Execution starts in the `if __name__ == "__main__":`
block at the bottom of this file, which calls main().
"""

import argparse                # reads command-line arguments
import os
import sys
from pathlib import Path       # file paths as objects (same code on Windows and Linux)

from job_analyzer.models import JobPosting
from job_analyzer.ranking import days_since_posted, priority
from job_analyzer.rules import InvalidPosting, initial_status, validate_posting
from job_analyzer.trim import extract_url_info, trim_page

MODEL = "claude-sonnet-5-5"
# __file__ = path of this file (…/job_analyzer/analyze.py).
# .resolve() makes it absolute; .parent goes up one level: job_analyzer/ → project root.
ROOT = Path(__file__).resolve().parent.parent
# Your real profile. It is listed in .gitignore: it holds personal data and never goes to GitHub.
CRITERIA = ROOT / "config" / "criteria.md"          # the / operator joins paths in pathlib
CRITERIA_EXAMPLE = ROOT / "config" / "criteria.example.md"
# Holds ANTHROPIC_API_KEY. Also in .gitignore.
ENV_FILE = ROOT / ".env"

# Triple quotes = multi-line string. A \ at the end of a line removes that line break
# from the final text (joins the line with the next one).
INSTRUCTIONS = """\
You analyze job postings for a candidate and return a structured job card.

The text is a LinkedIn page copied with Ctrl+A and may contain noise. Analyze ONLY the posting \
that has a full description (the one following "About the job"). Its title and company are the \
ones that appear right before that section. Ignore the list of other postings, menus and \
"similar jobs": they often contain similar titles from the same company.

Extraction rules:
- Extract only what the text says. If a piece of data is missing, use "not_mentioned" or null.
- visa: "citizenship_required" only if it demands citizenship or permanent residency \
(e.g. "must be a US citizen"). "No sponsorship" is "no_sponsorship". For postings in Mexico \
with no immigration restriction, use "not_applicable".
- clearance_itar: true if it asks for a security clearance, ITAR, EAR or "US person" status.
- application_type: "Responses managed off LinkedIn" or "people clicked apply" mean "external".
- linkedin_signals: only the ones from the closed list that appear in the text.
- The posting may be in Spanish or English; write free-text fields in English.

Scores (1–5) based on the candidate profile:
- technical_match: does the candidate meet the technical and experience requirements?
- domain_similarity: how close is the role to the candidate's field, per the scale in the profile?
They are different questions: a generic software role can have a good technical match and low \
domain similarity.

# Candidate profile and criteria

"""


class AnalysisError(RuntimeError):
    pass


def system_prompt(criteria_path: Path = CRITERIA) -> str:
    # Fixed instructions + your profile = the "system prompt".
    return INSTRUCTIONS + criteria_path.read_text(encoding="utf-8")


# `client=None` lets callers *inject* another client. In production the real one is
# created; tests pass a fake one that never touches the network (see tests/test_analyze.py).
# Same idea as SIL: the code under test does not know whether it talks to the real ECU or a model.
def analyze(text: str, model: str = MODEL, client=None, criteria_path: Path = CRITERIA) -> JobPosting:
    # Deferred import (inside the function): trim_page() and the tests do not need to load
    # the SDK, and --trim-only works even if the SDK is not installed.
    from anthropic import Anthropic

    client = client or Anthropic()        # Anthropic() reads ANTHROPIC_API_KEY from the environment
    resp = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        # The fixed block (instructions + profile) is cached; only the posting text changes.
        # Note: the API only caches above a minimum size; with a short criteria.md it may
        # not apply (nothing breaks, it just saves nothing).
        system=[{"type": "text", "text": system_prompt(criteria_path), "cache_control": {"type": "ephemeral"}}],
        # The conversation: a single user message with the already-trimmed posting.
        messages=[{"role": "user", "content": trim_page(text)}],
        # The SDK turns JobPosting into a JSON Schema and, on the way back, the JSON into a JobPosting.
        output_format=JobPosting,
        # effort: how much the model reasons. medium is enough for data extraction.
        output_config={"effort": "medium"},
        # If a safety classifier declines by mistake, the API retries on another model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    # stop_reason says why the model stopped. "end_turn" is normal; the other cases can
    # leave an incomplete answer or one outside the schema.
    if resp.stop_reason == "refusal":
        raise AnalysisError(f"The model declined the request: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise AnalysisError("Response cut off by max_tokens")
    if resp.parsed_output is None:
        raise AnalysisError(f"No job card returned (stop_reason={resp.stop_reason})")

    posting = resp.parsed_output          # already a JobPosting validated by Pydantic
    validate_posting(posting)             # 1–5 ranges (raises InvalidPosting otherwise)
    return posting


def _error(message: str) -> int:
    # Errors go to stderr, not stdout, so they never mix with the program's normal output.
    print(f"Error: {message}", file=sys.stderr)
    return 1


# `argv: list[str] | None = None`: by default argparse reads sys.argv (what you typed in
# the terminal). Tests can pass their own list, e.g. main(["capture.txt", "--trim-only"]).
def main(argv: list[str] | None = None) -> int:
    # 1. Define and read the command-line arguments.
    parser = argparse.ArgumentParser(prog="python -m job_analyzer.analyze", description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path, help="Captured posting (.txt)")       # positional: required
    parser.add_argument("--model", default=MODEL)                                   # optional with a value
    parser.add_argument("--trim-only", action="store_true",                         # flag: True if present
                        help="Print the trimmed text without calling the API")
    args = parser.parse_args(argv)        # "--trim-only" becomes args.trim_only

    # 2. Deterministic preprocessing (no AI, no cost).
    text = args.capture.read_text(encoding="utf-8")
    info = extract_url_info(text)   # before trim_page(): the URL line falls outside the trimmed text
    trimmed = trim_page(text)

    print(f"job_id: {info.job_id}  search: {info.search_query}")
    # {value:.0%} is a format spec: multiply by 100 and show 0 decimals with a % sign.
    print(f"trimmed: {len(trimmed)}/{len(text)} characters ({len(trimmed) / max(len(text), 1):.0%})")
    if args.trim_only:
        print("-" * 60)                   # "-" * 60 repeats the character 60 times
        print(trimmed)
        return 0

    # 3. Preconditions for the API call, checked up front so the errors are clear.
    if not CRITERIA.exists():
        return _error(f"config/{CRITERIA.name} not found. Copy config/{CRITERIA_EXAMPLE.name} and fill it in.")

    # Load the key from .env into THIS process's environment only. It is never set as a
    # Windows-wide variable (Claude Code would then bill as API instead of your subscription)
    # and it is never printed.
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _error("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")

    # 4. Call Claude. try/except catches each expected error, most specific first, and
    #    reports it without a traceback. API errors never echo the key.
    import anthropic

    try:
        posting = analyze(text, model=args.model)
    except (AnalysisError, InvalidPosting) as e:
        return _error(str(e))
    except anthropic.AuthenticationError:
        return _error("the API key was rejected. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.APIStatusError as e:            # any other HTTP error (429, 500, …)
        return _error(f"the Claude API returned HTTP {e.status_code}.")
    except anthropic.APIConnectionError:
        return _error("could not reach the Claude API. Check your connection.")

    # 5. Rules and ranking in Python.
    days = days_since_posted(posting.posted_ago)
    print(posting.model_dump_json(indent=2))         # Pydantic → indented JSON
    print(f"status: {initial_status(posting)}  days since posted: {days}  priority: {priority(posting, days):.2f}")
    return 0


# __name__ is "__main__" only when this file runs as the main program
# (python -m job_analyzer.analyze). When another module imports it (the tests, for
# example), __name__ is "job_analyzer.analyze" and this block does NOT run.
# sys.exit(n) ends the program with exit code n: 0 = success, anything else = error.
if __name__ == "__main__":
    sys.exit(main())

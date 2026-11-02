"""Deterministic (no AI) preprocessing of LinkedIn page captures.

Deterministic = same input, same output, every time. That is why these functions can be
covered by exact unit tests, unlike an LLM response.
"""

import re                                    # regular expressions: pattern matching on text
from dataclasses import dataclass            # generates __init__, __eq__ and __repr__ for us
from urllib.parse import parse_qs, urlparse  # split a URL into host, path and query parameters

# Module-level constants. UPPER_CASE by convention (PEP 8): Python does not prevent
# reassigning them, but the name signals that nobody should.
START_MARKER = "LinkedIn Corporation ©"
# Common prefix of "...other applicants" (Easy Apply) and "...others who clicked apply" (external apply).
END_MARKER = "See how you compare to"

# re.compile() parses the pattern once, at import time, and it is reused on every call.
# r"..." is a *raw string*: backslashes reach the regex as-is instead of being treated
# as Python escape sequences.
#   ^URL:   the line starts with "URL:" (^ = start of LINE thanks to re.MULTILINE)
#   \s*     zero or more whitespace characters
#   (\S+)   group 1: one or more non-whitespace characters → the full URL
URL_LINE_RE = re.compile(r"^URL:\s*(\S+)", re.MULTILINE)
#   (?:a|b) non-capturing group: matches "currentJobId=" or "/jobs/view/"
#   (\d+)   group 1: one or more digits → the job ID
JOB_ID_RE = re.compile(r"(?:currentJobId=|/jobs/view/)(\d+)")


# @dataclass is a *decorator*: it takes the class and adds methods to it automatically.
# frozen=True makes it immutable, like a const struct in C: `info.job_id = "x"` raises an error.
@dataclass(frozen=True)
class UrlInfo:
    job_id: str | None        # `str | None`: either text or None (same as Optional[str])
    url: str | None           # canonical: https://www.linkedin.com/jobs/view/<ID>/
    search_query: str | None  # the `keywords` parameter of the search the posting came from


def trim_page(text: str) -> str:
    """Keep only the open job posting. If a marker is missing, return the full text."""
    # str.find() returns the index of the first occurrence, or -1 if not found.
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    # Fallback: if LinkedIn changes its layout or UI language, sending everything
    # (more tokens) is better than losing the posting.
    if start == -1 or end == -1 or end < start:
        return text
    # Slicing: text[a:b] is the characters from a up to b-1.
    # `a` is one past the first line break after the marker, so the rest of that line
    # ("LinkedIn Corporation © 2026") is dropped too.
    return text[text.find("\n", start) + 1 : end]


def extract_url_info(text: str) -> UrlInfo:
    """Read the job ID and search query from the 'URL:' line added by F9. Call BEFORE trim_page()."""
    url_match = URL_LINE_RE.search(text)                  # a Match object, or None if nothing matched
    raw_url = url_match.group(1) if url_match else None   # conditional expression: X if cond else Y

    # Without a URL line, only short copies (a lone link) are searched: in a full page, a
    # /jobs/view/ link from the side list would return the ID of a different posting.
    # `a or b` returns `a` if it is "truthy" (not None, not empty); otherwise it returns `b`.
    source = raw_url or (text if len(text) < 500 else "")
    id_match = JOB_ID_RE.search(source)
    job_id = id_match.group(1) if id_match else None

    search_query = None
    if raw_url:
        # urlparse(url).query → "currentJobId=4123&keywords=Senior%20System..."
        # parse_qs(query)     → {"currentJobId": ["4123"], "keywords": ["Senior System ..."]}
        # parse_qs decodes %20 into a space. Each value is a list because a parameter can
        # appear more than once in a URL. .get() returns None when the key is missing.
        keywords = parse_qs(urlparse(raw_url).query).get("keywords")
        if keywords:
            search_query = keywords[0].strip() or None

    # f-string: f"...{job_id}..." inserts the variable's value into the text.
    url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else None
    return UrlInfo(job_id=job_id, url=url, search_query=search_query)

# How pytest works:
# - It looks for test_*.py files under tests/ and, inside them, for test_* functions.
# - Each function is one test case. If all its `assert` statements hold, it passes; if one
#   fails or the function raises an unexpected exception, it fails.
# - No main is needed: the "main" of the tests is the `pytest` command.
from pathlib import Path

import pytest

from job_analyzer.trim import UrlInfo, extract_url_info, trim_page, is_top_applicant

FIXTURES = Path(__file__).parent / "fixtures"
# .glob("**/*.txt") lists matching files in this folder and its subfolders, so real
# captures saved in fixtures/private/ join test_trim_keeps_only_the_posting automatically.
CAPTURES = sorted(FIXTURES.glob("**/*.txt"))


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_no_markers_returns_full_text():
    text = "A posting without LinkedIn's markers."
    assert trim_page(text) == text


def test_markers_in_reverse_order_return_full_text():
    text = "See how you compare to x\nLinkedIn Corporation © 2026\nrest"
    assert trim_page(text) == text


# parametrize runs the same test once per item in the list, like test vectors on a HIL
# bench: same sequence, different stimuli.
# ids=lambda p: p.name names each case after its file in the report.
# (lambda is a one-line anonymous function: lambda p: p.name ≈ def f(p): return p.name)
@pytest.mark.parametrize("capture", CAPTURES, ids=lambda p: p.name)
def test_trim_keeps_only_the_posting(capture):
    text = capture.read_text(encoding="utf-8")
    trimmed = trim_page(text)
    assert len(trimmed) < len(text)
    assert "About the job" in trimmed
    assert "LinkedIn Corporation ©" not in trimmed
    assert "See how you compare to" not in trimmed
    assert "Skip to main content" not in trimmed


def test_easy_apply_variant():
    trimmed = trim_page(read("synthetic_easy_apply.txt"))
    assert trimmed.startswith("Automation Tester Mid.\n")
    assert "Automation Tester Mid. QRO" not in trimmed   # similar title from the side list
    assert "Jane Doe" not in trimmed                     # the signed-in user's name at the bottom


def test_external_apply_variant():
    trimmed = trim_page(read("synthetic_external.txt"))
    assert trimmed.startswith("2714 Ingeniero de confiabilidad")
    assert "Sr. Firmware Engineer" not in trimmed
    assert "Jane Doe" not in trimmed


def test_fewer_than_3_applicants_variant():
    text = "menu\nLinkedIn Corporation © 2026\nPOSTING\nOnce there are 3 or more applicants for this job, we will show how you compare to the competition.\nfooter"
    assert trim_page(text) == "POSTING\n"


def test_url_info_from_url_line():
    info = extract_url_info(read("synthetic_external.txt"))
    assert info.job_id == "4123456789"
    assert info.url == "https://www.linkedin.com/jobs/view/4123456789/"
    assert info.search_query == "Senior System Test Engineer automotive safety"


def test_url_info_is_lost_if_trimmed_first():
    text = read("synthetic_external.txt")
    assert extract_url_info(trim_page(text)).job_id is None


def test_no_url():
    assert extract_url_info(read("synthetic_easy_apply.txt")) == UrlInfo(None, None, None)


def test_single_posting_url():
    info = extract_url_info("URL: https://www.linkedin.com/jobs/view/3999888777/?refId=abc\n\ntext")
    assert info.job_id == "3999888777"
    assert info.search_query is None


def test_bare_link_without_url_line():
    assert extract_url_info("https://www.linkedin.com/jobs/view/3999888777/").job_id == "3999888777"


def test_long_page_without_url_does_not_take_id_from_side_list():
    text = "x" * 600 + " https://www.linkedin.com/jobs/view/111/ "
    assert extract_url_info(text).job_id is None


@pytest.mark.parametrize("text, expected", [
    ("You’d be a top applicant", True),
    ("Job match is high, we can help you stand out", True),
    ("", False),
])
def test_is_top_applicant(text, expected):
    assert is_top_applicant(text) == expected


def test_fewer_than_3_candidates_variant():
    text = "menu\nLinkedIn Corporation © 2026\nPOSTING\nOnce there are 3 or more candidates for this job, we will show how you compare to the competition.\nfooter"
    assert trim_page(text) == "POSTING\n"

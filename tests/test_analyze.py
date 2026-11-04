from pathlib import Path
from types import SimpleNamespace

import pytest

from job_analyzer import analyze as mod
from tests.test_ranking import posting


# A "test double" (stub): it replaces the real Anthropic client so analyze() can be
# tested without network, without cost and with controlled responses. Same idea as SIL:
# the code under test believes it talks to the real system, but it talks to a model.
class FakeClient:
    """Mimics client.beta.messages.parse without network."""

    # __init__ is the constructor: it runs on FakeClient(resp).
    # `self` is the instance being built (like `this` in C++).
    def __init__(self, resp):
        self.resp = resp          # the response we pretend the API returned
        self.kwargs = None        # the arguments we were called with are stored here
        # SimpleNamespace builds an object with whatever attributes you pass. This sets
        # up the client.beta.messages.parse(...) chain that analyze() uses.
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    # **kwargs receives every keyword argument (model=..., system=...) in a dict.
    def parse(self, **kwargs):
        self.kwargs = kwargs      # saved so the test can check them with assert
        return self.resp


def run(resp, text="text"):
    # The public example profile is used so the tests never depend on your private criteria.md.
    client = FakeClient(resp)
    mod.analyze(text, client=client, criteria_path=mod.CRITERIA_EXAMPLE)
    return client.kwargs


def test_call_uses_trimmed_text_cache_and_schema():
    text = "menu\nLinkedIn Corporation © 2026\nPOSTING\nSee how you compare to x\nfooter"
    kw = run(SimpleNamespace(stop_reason="end_turn", parsed_output=posting()), text)
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["messages"][0]["content"] == "POSTING\n"
    assert kw["output_format"] is mod.JobPosting
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["system"][0]["text"].startswith(mod.INSTRUCTIONS)
    assert "My field (for `domain_similarity`)" in kw["system"][0]["text"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_abnormal_stop_reason(stop_reason):
    with pytest.raises(mod.AnalysisError):
        run(SimpleNamespace(stop_reason=stop_reason, stop_details=None, parsed_output=None))


def test_out_of_range_score_is_rejected():
    with pytest.raises(ValueError):
        run(SimpleNamespace(stop_reason="end_turn", parsed_output=posting(technical_match=7)))


def test_schema_is_compatible_with_structured_outputs():
    from anthropic.lib._parse._transform import to_json_output_format

    schema = to_json_output_format(mod.JobPosting)["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(mod.JobPosting.model_fields)


# --- CLI (main) -------------------------------------------------------------------
# monkeypatch is a pytest *fixture*: pytest sees the parameter name and passes it in.
# It changes variables or environment only for this test and restores them afterwards.
# capsys captures what the program prints to stdout/stderr.

CAPTURE = str(Path(__file__).parent / "fixtures" / "synthetic_external.txt")


def test_main_trim_only_never_calls_the_api(capsys):
    assert mod.main([CAPTURE, "--trim-only"]) == 0
    out = capsys.readouterr().out
    assert "job_id: 4123456789" in out
    assert "URL: https://www.linkedin.com/jobs/view/4123456789/" in out


def test_main_without_api_key_fails_before_calling_the_api(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(mod, "ENV_FILE", tmp_path / ".env")        # a .env that does not exist
    monkeypatch.setattr(mod, "CRITERIA", mod.CRITERIA_EXAMPLE)
    # If main() reached analyze(), this would make the test fail loudly.
    monkeypatch.setattr(mod, "analyze", lambda *a, **k: pytest.fail("analyze() must not be called"))
    assert mod.main([CAPTURE]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_main_without_criteria_fails(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(mod, "CRITERIA", tmp_path / "criteria.md")
    assert mod.main([CAPTURE]) == 1
    assert "criteria.md not found" in capsys.readouterr().err


def test_top_applicant_is_added_when_claude_misses_it():
    text = "menu\nLinkedIn Corporation © 2026\nYou’d be a top applicant\nSee how you compare to x\nfooter"
    resp = SimpleNamespace(stop_reason="end_turn", parsed_output=posting(linkedin_signals=[]))
    result = mod.analyze(text, client=FakeClient(resp), criteria_path=mod.CRITERIA_EXAMPLE)
    assert "top_applicant" in result.linkedin_signals


def test_top_applicant_is_in_the_side_list_is_ignored():
    text = "You’d be a top applicant\nLinkedIn Corporation © 2026\nPOSTING\nSee how you compare to x\nfooter"
    resp = SimpleNamespace(stop_reason="end_turn", parsed_output=posting(linkedin_signals=[]))
    result = mod.analyze(text, client=FakeClient(resp), criteria_path=mod.CRITERIA_EXAMPLE)
    assert "top_applicant" not in result.linkedin_signals


def test_top_applicant_is_already_in_the_signals_is_ignored():
    text = "menu\nLinkedIn Corporation © 2026\nYou’d be a top applicant\nSee how you compare to x\nfooter"
    resp = SimpleNamespace(stop_reason="end_turn", parsed_output=posting(linkedin_signals=["top_applicant"]))
    result = mod.analyze(text, client=FakeClient(resp), criteria_path=mod.CRITERIA_EXAMPLE)
    assert result.linkedin_signals.count("top_applicant") == 1
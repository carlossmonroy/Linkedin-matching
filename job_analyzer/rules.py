"""Hard rules and validations in Python, not in the LLM.

Decisions that must not fail (discarding for citizenship or clearance) are made by
deterministic code. The LLM only extracts the data; Python decides.
"""

from job_analyzer.models import JobPosting, Status


# Custom exception: inheriting from ValueError lets callers catch it as InvalidPosting
# (specific) or as ValueError (generic).
class InvalidPosting(ValueError):
    pass                                  # `pass` = empty body; the class adds nothing


def validate_posting(p: JobPosting) -> None:
    """Structured outputs do not support minimum/maximum: ranges are checked here."""
    for field in ("technical_match", "domain_similarity"):
        value = getattr(p, field)         # getattr(obj, "x") is obj.x with the name given as text
        if not 1 <= value <= 5:           # chained comparison: 1 <= value and value <= 5
            # raise throws the exception: the function stops and the error goes up to the caller.
            raise InvalidPosting(f"{field}={value} is outside 1–5")


def initial_status(p: JobPosting) -> Status:
    # "no_sponsorship" does NOT discard: a TN visa may still apply. Only impossible
    # postings are discarded.
    if p.clearance_itar or p.visa == "citizenship_required":
        return "discarded"
    # If the posting rejects candidates who would need to relocate, it is discarded
    # unless the posting is in Mexico (the candidate lives in Mexico).
    elif p.local_candidates_only and p.country != "mexico":
        return "discarded"
    return "to_review"

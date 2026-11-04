"""Schema of the job card Claude returns (structured output) and the posting statuses.

The JobPosting class does two jobs at once:
1. The Anthropic SDK turns it into a JSON Schema and sends it to the API. The API
   guarantees that Claude answers with JSON that matches that schema.
2. Pydantic validates that JSON while turning it back into a JobPosting object.
   If a type does not match (e.g. text where an int belongs) it raises ValidationError.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Literal["a", "b"] = only exactly those values are accepted (a closed enum).
# In the JSON Schema it becomes {"enum": [...]}, so Claude cannot invent another signal
# and the ranking can compare them without worrying about casing or synonyms.
Signal = Literal[
    "top_applicant",        # "You'd be a top applicant"
    "actively_reviewing",   # "Actively reviewing applicants"
    "early_applicant",      # "Be an early applicant"
    "reposted",             # "Reposted ..."
    "connections",          # people in my network work at the company
    "alumni",               # former colleagues / alumni of my school work at the company
    "promoted",             # "Promoted"
]

# Posting state machine (section 4 of the design doc). Phase 1 only uses "discarded"
# and "to_review"; the rest arrives with the database (phase 2).
Status = Literal[
    "new", "analyzed", "discarded", "to_review", "preparing",
    "applied", "interview", "rejected", "no_response",
]


class Requirement(BaseModel):
    """A single requirement from the posting, e.g. 'Python' or 'Bachelor's degree'."""
    text: str
    importance: Literal["required", "preferred"] = Field(description="required: the posting demands it (required, basic or minimum qualifications). preferred: anything optional (preferred, nice to have, a plus)")
    status: Literal["met", "partial", "missing"] = Field(description="met: direct documented experience. partial: minimal or transferable experience. missing: nothing documented or transferable")
    evidence: str | None = Field(description="Brief evidence from the candidate profile; null if status is missing")


# Inheriting from BaseModel gives the class validation, model_dump_json(), etc.
# Every attribute with a type annotation (`name: type`) becomes a required field.
class JobPosting(BaseModel):
    company: str
    title: str
    # Field(description=...) does not change the type: the text travels inside the
    # JSON Schema and Claude reads it as an instruction for that field.
    location: str = Field(description="Location text exactly as it appears in the posting")
    city: str | None = Field(description="City name only, without state or country")
    country: Literal["mexico", "usa", "other", "not_mentioned", "germany", "canada", "switzerland"]
    work_mode: Literal["onsite", "hybrid", "remote", "not_mentioned"]
    visa: Literal["sponsors", "no_sponsorship", "citizenship_required", "not_mentioned", "not_applicable"]
    clearance_itar: bool = Field(description="Requires a security clearance, ITAR, EAR or 'US person' status")
    local_candidates_only: bool = Field(description="True if the posting rejects candidates who would need to relocate")
    language_requirement: str = Field(description="Required language and level, e.g. 'English B2', or 'not_mentioned'")
    seniority: Literal["entry", "mid", "senior", "lead", "not_mentioned"]
    years_experience: int | None
    requirements: list[Requirement] = Field(description="One item per skill, tool, experience or education requirement in the posting. Exclude location, visa, clearance and language: they have their own fields")
    tech_stack: list[str]
    application_type: Literal["easy_apply", "external", "not_mentioned"]
    applicants: int | None = Field(description="'43 applicants' or '42 people clicked apply' → 43 / 42")
    posted_ago: str | None = Field(description="Literal text, e.g. 'Reposted 2 days ago'")
    linkedin_signals: list[Signal]                # a list whose items can only be a Signal
    # Structured outputs do not support minimum/maximum in the schema: the 1–5 range
    # is checked in Python, in rules.validate_posting().
    technical_match: int = Field(description="1–5: does the candidate meet the requirements?")
    domain_similarity: int = Field(description="1–5: how close is the role to the candidate's field?")
    rationale: str = Field(description="2–3 sentences justifying both scores")

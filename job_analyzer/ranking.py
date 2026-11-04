"""Priority computed in Python (transparent and tunable), not by the LLM.

priority = fit (is this job for me?) + opportunity (do I have a real chance now?)
           + location adjustment (do I want to live there?)
           + salary penalty (does it pay below my floor?)
"""

import re

from job_analyzer.models import JobPosting

W_LOCATION = 0.3   # weight of the location axis; tuned with data (section 6 of the design doc)
W_LOW_SALARY = -1.0  # penalty below the salary floor; larger than the run-to-run noise measured (0.9)

# Dictionary {unit prefix: days per unit}. The Spanish words are data, not names:
# postings in Spanish say "hace 3 días".
# Since Python 3.7 dictionaries keep insertion order, and the loop in
# days_since_posted() stops at the FIRST prefix that matches.
_DAYS_PER_UNIT = {
    "minute": 0, "minuto": 0, "min": 0,
    "hour": 0, "hora": 0, "hr": 0,
    "day": 1, "día": 1, "dia": 1,
    "week": 7, "semana": 7, "wk": 7,
    "month": 30, "mes": 30, "mo": 30,
    "year": 365, "año": 365, "ano": 365, "yr": 365,
}
# A leading underscore (_QUANTITY_RE) is the "module private" convention: it is not
# part of what other modules are meant to import.
#   \b             word boundary (avoids grabbing the trailing "a" of another word)
#   (\d+|an?|una?) group 1: a number, or "a"/"an"/"un"/"una" (all worth 1)
#   \s*\+?\s*      spaces and an optional "+" ("30+ days")
#   (minutos?|…)   group 2: the unit; "s?" = the trailing "s" is optional
#   \b             the unit ends there
_QUANTITY_RE = re.compile(
    r"\b(\d+|an?|una?)\s*\+?\s*"
    r"(minutos?|minutes?|mins?|horas?|hours?|hrs?|días?|dias?|days?|semanas?|weeks?|wks?"
    r"|meses|mes|months?|mos?|años?|anos?|years?|yrs?)\b",
    re.IGNORECASE,
)


def days_since_posted(text: str | None) -> int | None:
    """'2 days ago', 'Reposted 1 week ago', 'hace 3 días'… → days. None if not recognized."""
    if not text:                          # covers None and "" at once
        return None
    t = text.lower()
    if re.search(r"\b(just now|today|hoy|justo ahora|recién|recien)\b", t):
        return 0
    if re.search(r"\b(yesterday|ayer)\b", t):
        return 1
    m = _QUANTITY_RE.search(t)
    if not m:
        return None
    number = m.group(1)
    quantity = int(number) if number.isdigit() else 1   # "a day" / "una semana" = 1
    unit = m.group(2).lower()
    # .items() yields (key, value) pairs; the for loop unpacks them into two variables.
    for prefix, days in _DAYS_PER_UNIT.items():
        if unit.startswith(prefix):
            return quantity * days
    return None


def recency_weight(days: int | None) -> float:
    """Newer postings weigh more: applying in the first days makes it likelier a human reads the CV."""
    if days is None:
        return 0.0
    if days <= 3:
        return 0.5
    if days <= 7:
        return 0.3
    if days <= 14:
        return 0.0
    if days <= 30:
        return -0.2
    return -0.4


def fit(p: JobPosting) -> float:
    # Range: 0.9 (both scores at 1) to 4.5 (both at 5). Domain similarity weighs more.
    return 0.5 * p.domain_similarity + 0.4 * p.technical_match


def opportunity(p: JobPosting, days: int | None) -> float:
    # Range: -0.4 (old, no signals) to 0.9 (recent + top applicant + actively reviewing).
    score = recency_weight(days)
    if "top_applicant" in p.linkedin_signals:      # `in` checks whether the list contains the item
        score += 0.2
    if "actively_reviewing" in p.linkedin_signals:
        score += 0.2
    return score


# `location: float | None = None` is a parameter with a default value: it can be omitted.
def priority(p: JobPosting, days: int | None, location: float | None = None, floors: dict[str, dict[str, float]] | None = None) -> float:
    score = fit(p) + opportunity(p, days)
    if location is not None:                  # remote or no data → neutral
        score += W_LOCATION * (location - 3)  # centered on 3: a good city adds, a bad one subtracts
    if below_salary_floor(p, floors or {}):   # `floors or {}`: no floors → an empty dictionary
        score += W_LOW_SALARY
    return score


def below_salary_floor(p: JobPosting, floors: dict[str, dict[str, float]]) -> bool:
    """True if the posting's salary is below the candidate's minimum."""
    floor = floors.get(p.salary_currency, {}).get(p.salary_period)
    if floor is None or p.salary_max is None:
        return False
    return p.salary_max < floor

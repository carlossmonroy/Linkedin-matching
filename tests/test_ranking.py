import pytest

from job_analyzer.models import JobPosting
from job_analyzer.ranking import days_since_posted, opportunity, priority, recency_weight, below_salary_floor
from job_analyzer.rules import InvalidPosting, initial_status, validate_posting


# Test vector table: (input, expected output). Supporting a new LinkedIn format means
# adding one line here and seeing whether it passes.
@pytest.mark.parametrize("text, days", [
    ("2 days ago", 2),
    ("1 day ago", 1),
    ("Reposted 1 week ago", 7),
    ("Reposted 3 weeks ago", 21),
    ("5 hours ago", 0),
    ("30 minutes ago", 0),
    ("1 month ago", 30),
    ("2 months ago", 60),
    ("1 year ago", 365),
    ("a day ago", 1),
    ("an hour ago", 0),
    ("hace 3 días", 3),
    ("hace 1 día", 1),
    ("hace 2 semanas", 14),
    ("hace una semana", 7),
    ("hace 2 horas", 0),
    ("hace 1 mes", 30),
    ("hace 3 meses", 90),
    ("Publicado de nuevo hace 1 semana", 7),
    ("ALTEN · Querétaro · 2 days ago · 43 applicants", 2),
    ("just now", 0),
    ("hoy", 0),
    ("yesterday", 1),
])
def test_days_since_posted(text, days):
    assert days_since_posted(text) == days


@pytest.mark.parametrize("text", [None, "", "no date here"])
def test_days_since_posted_unknown(text):
    assert days_since_posted(text) is None


def test_recency_weight_boundaries():
    assert [recency_weight(d) for d in (None, 0, 3, 4, 7, 8, 14, 15, 30, 31)] == \
        [0.0, 0.5, 0.5, 0.3, 0.3, 0.0, 0.0, -0.2, -0.2, -0.4]


# Factory of job cards for the tests. **changes collects any keyword arguments into a
# dictionary: posting(visa="no_sponsorship") → changes = {"visa": "no_sponsorship"}.
# {**base, **changes} merges both dictionaries; values in `changes` override `base`.
# This way each test only writes the field it cares about.
def posting(**changes) -> JobPosting:
    base = dict(
        company="ALTEN", title="Automation Tester Mid.", location="Querétaro, Mexico",
        city="Querétaro", country="mexico", work_mode="hybrid", visa="not_applicable",
        clearance_itar=False, local_candidates_only=False, language_requirement="not_mentioned", seniority="mid",
        years_experience=3, salary_min=None, salary_max=None, salary_currency=None, salary_period=None,
        requirements=[], tech_stack=["HIL", "BDD"],
        application_type="easy_apply", applicants=43, posted_ago="2 days ago",
        linkedin_signals=[], technical_match=4, domain_similarity=5, rationale="",
    )
    return JobPosting(**{**base, **changes})


def test_opportunity_adds_signals():
    p = posting(linkedin_signals=["top_applicant", "actively_reviewing"])
    # pytest.approx compares floats with a tolerance: 0.1 + 0.2 != 0.3 exactly in binary.
    assert opportunity(p, 2) == pytest.approx(0.5 + 0.2 + 0.2)


def test_priority_location_centered_on_3():
    p = posting()
    assert priority(p, None, 3.0) == pytest.approx(priority(p, None, None))
    assert priority(p, None, 5.0) > priority(p, None, None) > priority(p, None, 1.0)


@pytest.mark.parametrize("changes, status", [
    ({}, "to_review"),
    ({"clearance_itar": True}, "discarded"),
    ({"visa": "citizenship_required"}, "discarded"),
    ({"visa": "no_sponsorship", "country": "mexico"}, "to_review"),   # no sponsor needed in Mexico
    ({"visa": "no_sponsorship", "country": "usa"}, "discarded"),
    ({"local_candidates_only": True, "country": "usa"}, "discarded"),
    ({"local_candidates_only": True, "country": "mexico"}, "to_review"),
    ({"local_candidates_only": False, "country": "usa"}, "to_review"),
])
def test_initial_status(changes, status):
    assert initial_status(posting(**changes)) == status


# Two stacked parametrize decorators = Cartesian product: 2 fields × 2 values = 4 cases.
@pytest.mark.parametrize("field", ["technical_match", "domain_similarity"])
@pytest.mark.parametrize("value", [0, 6])
def test_validate_posting_out_of_range(field, value):
    # `with pytest.raises(X):` the test passes only if the block raises X.
    with pytest.raises(InvalidPosting):
        validate_posting(posting(**{field: value}))


FLOORS= {"USD":{"year": 1000, "hour": 10},
         "MXN":{"month": 5000}}

@pytest.mark.parametrize("salary_max, currency, period, expected", [
    (999, "USD", "year", True),
    (1000, "USD", "year", False),    # equal to the floor is not below it
    (None, None, None, False),       # no salary in the posting
    (9, "USD", "hour", True),
    (11, "USD", "hour", False),
    (499, "MXN", "month", True),
    (5001, "MXN", "month", False),
    (50, "CAD", "year", False),      # no floor for that currency
    (50, "USD", "month", False),     # no floor for that period
])
def test_below_salary_floor(salary_max, currency, period, expected):
    p = posting(salary_max=salary_max, salary_currency=currency, salary_period=period)
    assert below_salary_floor(p, FLOORS) is expected


def test_priority_penalizes_low_salary():
    p = posting(salary_max=999, salary_currency="USD", salary_period="year")
    # The posting is below the floor, so it is penalized. The penalty is not huge: the
    # candidate may still apply if the company is flexible.
    assert priority(p, None, floors=FLOORS) == pytest.approx(priority(p, None) - 1.0)


def test_priority_ignores_salary_at_the_floor():
    p = posting(salary_max=1000, salary_currency="USD", salary_period="year")
    assert priority(p, None, floors=FLOORS) == pytest.approx(priority(p, None))
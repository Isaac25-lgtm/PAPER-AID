"""Sample sizes, calculated by code from the student's own assumptions (Codex review P0: a model
must never supply a population size or pick numbers for a calculation). The writer receives the
result and the steps and may only restate them.

Formulas, as commonly taught and cited:
- Yamane (1967): n = N / (1 + N·e²)
- Cochran (1977): n₀ = z²·p(1−p) / e², with the finite population correction n = n₀ / (1 + (n₀ − 1)/N)
  when N is known
- Krejcie & Morgan (1970): n = χ²·N·p(1−p) / (e²(N−1) + χ²·p(1−p)), χ² = 3.841 at 95% confidence
- Census: every member of the population
Qualitative studies use saturation or a number the student states, with its rationale."""

import math
from dataclasses import dataclass

from app.proposals.models import SampleSize

Z = {90: 1.645, 95: 1.96, 99: 2.576}
CHI_SQUARE = {90: 2.706, 95: 3.841, 99: 6.635}  # one degree of freedom


@dataclass(frozen=True)
class SampleResult:
    size: int | None  # None: not applicable or not calculable
    steps: str  # the calculation as it should appear in the proposal
    figures: str  # every figure used, so the figure check accepts them in Chapter Three
    missing: str = ""  # what the student must supply before Chapter Three can be written


def _pct(value: float) -> str:
    return f"{value * 100:g}%"


def calculate(s: SampleSize) -> SampleResult:
    e, p, level, n_pop = s.margin, s.proportion, s.confidence, s.population
    if s.method == "NOT_APPLICABLE":
        return SampleResult(None, "", "")
    if s.method in ("SATURATION", "AUTHOR_STATED"):
        if s.stated is None:
            what = "an expected number of participants" if s.method == "SATURATION" else "the sample size"
            return SampleResult(None, "", "", missing=f"State {what} and why it is enough.")
        if s.method == "SATURATION":
            steps = f"Participants will be recruited until data saturation is reached, expected at about {s.stated}."
        else:
            steps = f"The sample will comprise {s.stated} participants."
        return SampleResult(s.stated, f"{steps} {s.rationale}".strip(), f"{s.stated} {s.rationale}")
    if s.method == "CENSUS":
        if n_pop is None:
            return SampleResult(None, "", "", missing="Give the size of the population you will study in full, and where the figure comes from.")
        return SampleResult(n_pop, f"All {n_pop:,} members of the population will be studied (a census).", f"{n_pop} {s.population_source}")
    if s.method in ("YAMANE", "KREJCIE_MORGAN") and n_pop is None:
        return SampleResult(None, "", "", missing="Give the size of the accessible population (N) and where the figure comes from; the formula needs it.")
    if s.method == "YAMANE":
        assert n_pop is not None
        size = math.ceil(n_pop / (1 + n_pop * e**2))
        steps = f"Using Yamane's (1967) formula, n = N / (1 + N·e²), with N = {n_pop:,} and e = {e:g} ({_pct(e)} margin of error): n = {n_pop:,} / (1 + {n_pop:,} × {e:g}²) ≈ {size:,}."
        return SampleResult(size, steps, f"{n_pop} {e:g} {_pct(e)} {size} 1967 2")
    if s.method == "KREJCIE_MORGAN":
        assert n_pop is not None
        chi = CHI_SQUARE[level]
        size = math.ceil(chi * n_pop * p * (1 - p) / (e**2 * (n_pop - 1) + chi * p * (1 - p)))
        steps = (
            f"Using Krejcie and Morgan's (1970) formula, n = χ²NP(1−P) / (d²(N−1) + χ²P(1−P)), with χ² = {chi} ({level}% confidence), "
            f"N = {n_pop:,}, P = {p:g} and d = {e:g}: n ≈ {size:,}."
        )
        return SampleResult(size, steps, f"{chi} {level} {level}% {n_pop} {p:g} {e:g} {size} 1970 2 1")
    z = Z[level]
    n0 = z**2 * p * (1 - p) / e**2
    if n_pop is None:
        size = math.ceil(n0)
        steps = f"Using Cochran's (1977) formula, n = z²p(1−p) / e², with z = {z} ({level}% confidence), p = {p:g} and e = {e:g}: n = {z}² × {p:g} × {1 - p:g} / {e:g}² ≈ {size:,}."
        return SampleResult(size, steps, f"{z} {level} {level}% {p:g} {1 - p:g} {e:g} {size} 1977 2")
    corrected = math.ceil(n0 / (1 + (n0 - 1) / n_pop))
    steps = (
        f"Using Cochran's (1977) formula, n₀ = z²p(1−p) / e², with z = {z} ({level}% confidence), p = {p:g} and e = {e:g}, gives n₀ ≈ {n0:.1f}; "
        f"adjusted for the population of N = {n_pop:,}, n = n₀ / (1 + (n₀ − 1)/N) ≈ {corrected:,}."
    )
    return SampleResult(corrected, steps, f"{z} {level} {level}% {p:g} {1 - p:g} {e:g} {n0:.1f} {n_pop} {corrected} 1977 2 1")


def needs_numbers(study_type: str) -> bool:
    """Quantitative and mixed studies need a sample size calculation or a census."""
    return study_type in ("QUANTITATIVE", "MIXED")

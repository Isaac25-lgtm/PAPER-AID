"""The one pricing formula. The browser only ever displays what this returns."""

import math
from dataclasses import dataclass

from app.jobs.models import QuoteLine, ServiceSelection

PRICING_VERSION = "v1"


@dataclass(frozen=True)
class Rule:
    minimum: int
    base: int
    per_1k_words: int


RULES = {
    "AI_CHECK": Rule(2000, 1500, 300),
    "REFINE_LIGHT": Rule(4000, 2500, 700),
    "REFINE_STANDARD": Rule(4000, 2500, 1000),
    "REDRAFT": Rule(10000, 5000, 2000),
    "FORMAT": Rule(3000, 3000, 150),
    "TEMPLATE_FORMAT": Rule(5000, 4000, 200),
    "LATEX": Rule(6000, 5000, 200),
}

# "From" prices shown on the public site; the minimum each service can cost.
INDICATIVE_FROM = {
    "AI_CHECK": RULES["AI_CHECK"].minimum,
    "REFINE": RULES["REFINE_STANDARD"].minimum,
    "FORMAT": RULES["FORMAT"].minimum,
    "TEMPLATE_FORMAT": RULES["TEMPLATE_FORMAT"].minimum,
    "REDRAFT": RULES["REDRAFT"].minimum,
    "LATEX": RULES["LATEX"].minimum,
}


def _price(rule: Rule, words: int) -> int:
    raw = max(rule.minimum, rule.base + rule.per_1k_words * math.ceil(words / 1000))
    return math.ceil(raw / 500) * 500


def quote_lines(selection: ServiceSelection, words: int) -> list[QuoteLine]:
    lines: list[QuoteLine] = []
    if selection.writing == "AI_CHECK":
        lines.append(QuoteLine(label="AI Check", amount=_price(RULES["AI_CHECK"], words)))
    elif selection.writing == "REFINE":
        light = selection.intensity == "LIGHT"
        rule = RULES["REFINE_LIGHT" if light else "REFINE_STANDARD"]
        lines.append(QuoteLine(label=f"Check + Refine ({'light' if light else 'standard'})", amount=_price(rule, words)))
    elif selection.writing == "REDRAFT":
        lines.append(QuoteLine(label="Deep redraft", amount=_price(RULES["REDRAFT"], words)))
    if selection.formatting == "FORMAT":
        lines.append(QuoteLine(label="Academic formatting", amount=_price(RULES["FORMAT"], words)))
    elif selection.formatting == "TEMPLATE_FORMAT":
        lines.append(QuoteLine(label="University template formatting", amount=_price(RULES["TEMPLATE_FORMAT"], words)))
    if selection.latex:
        lines.append(QuoteLine(label="LaTeX conversion", amount=_price(RULES["LATEX"], words)))
    return lines

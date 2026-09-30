"""Requirements read from the student's documents (rulebook §5). A model proposes each requirement
with its exact quote and where it was found; code then checks the quote is really in that document.
Only a confirmed quote can lock a requirement; anything else is shown to the student to confirm
(Codex review 2026-09-30, amendment 4: the model's own confidence decides nothing)."""

import re
import secrets
from typing import Any

from app.works.models import Requirement, SourceFile

# The vocabulary the reader may use, with the plain label students see and whether a mistake here
# would be costly enough that the student always confirms it (rulebook §5.1).
KEYS: dict[str, tuple[str, bool]] = {
    "limit.words": ("Word limit", True),
    "limit.words_min": ("Minimum length in words", False),
    "limit.pages": ("Page limit", True),
    "limit.characters": ("Character limit", True),
    "tolerance": ("Allowed tolerance on the length", False),
    "field": ("Application form box", True),
    "section.required": ("Required section or heading", False),
    "template.heading": ("Template heading, in order", False),
    "annex": ("Required annex", False),
    "eligibility": ("Eligibility criterion", True),
    "ceiling": ("Funding ceiling", True),
    "minimum_request": ("Minimum request", False),
    "currency": ("Currency", False),
    "duration_months": ("Project duration", False),
    "deadline": ("Deadline", True),
    "cost_share": ("Required cost share", True),
    "indirect_rate": ("Indirect cost rate", True),
    "prohibited_cost": ("Cost the call does not allow", True),
    "priority": ("Funder priority area", False),
    "scoring": ("Scoring criterion", False),
    "overlay": ("Cross-cutting theme to address", False),
    "output_indicators": ("Outputs need indicators", False),
    "disaggregation": ("Indicators must be disaggregated", False),
    "theory_of_change": ("A Theory of Change is required", False),
    "evaluation": ("An evaluation is required", False),
    "citation_style": ("Referencing style", False),
    "ai_policy": ("Rule on using AI", True),
    "source_policy": ("Which sources may be used", False),
    "required_reading": ("Required reading", False),
    "directive": ("What the question asks you to do", False),
    "subquestion": ("Part of the question", False),
    "subject": ("Subject of the question", False),
    "limiting": ("Limit on the question (place, period, group)", False),
    "rubric": ("Marking criterion", False),
    "learning_outcome": ("Learning outcome", False),
    "level": ("Academic level", False),
    "format": ("Formatting instruction", False),
    "coursework_type": ("Type of assignment", False),
}
SOURCE_ROLES = ("CALL", "TEMPLATE", "ADDENDUM", "BRIEF", "RUBRIC", "READING", "GUIDE", "OTHER")

# What the reader returns (strict: every field required, nothing extra).
_S, _N = {"type": "string"}, {"type": ["number", "null"]}
READ_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sourceId": _S, "key": {"type": "string", "enum": list(KEYS)}, "value": _S, "number": _N, "unit": _S, "hard": {"type": "boolean"},
                    "quote": _S, "location": _S, "weight": _N, "countsToward": {"type": "array", "items": _S}, "amends": {"type": "boolean"},
                },
                "required": ["sourceId", "key", "value", "number", "unit", "hard", "quote", "location", "weight", "countsToward", "amends"],
                "additionalProperties": False,
            },
        },
        "unclear": {"type": "array", "items": _S},
    },
    "required": ["requirements", "unclear"],
    "additionalProperties": False,
}
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")


def _words(text: str) -> list[str]:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.findall(r"\w+|%|\$|€|£", text.casefold())


def quote_found(quote: str, text: str) -> bool:
    """The quote is in the text word for word (typography, case, spacing and line-end hyphenation
    aside). A quote shortened with an ellipsis must have every part, in order. At least two words:
    a single word could be found anywhere."""
    parts = [_words(p) for p in ELLIPSIS.split(quote) if p.strip()]
    if not parts or sum(len(p) for p in parts) < 2:
        return False
    haystack = " " + " ".join(_words(text)) + " "
    position = 0
    for part in parts:
        found = haystack.find(" " + " ".join(part) + " ", position)
        if found < 0:
            return False
        position = found + 1
    return True


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
                "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1_000, "k": 1_000, "million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000}
# A figure read whole: "1,500" is 1,500 (never 1 and 500) and "50k" is 50,000 (never 50).
FIGURE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:[ \u00a0]?(hundred|thousand|million|billion|bn|k|m)\b)?", re.IGNORECASE)
WORD = re.compile(r"[a-z]+")
# What a quote must also name for its value to count as read (Codex audit 2026-09-30 #10).
UNIT_WORDS = {"limit.words": ("word",), "limit.words_min": ("word",), "limit.pages": ("page", "side"), "limit.characters": ("character", "char")}
UNIT_GAP = 14  # characters between a limit's number and its unit ("1,500 words", "5-page", "2,000-word maximum")
STYLE_WORDS = ("apa", "harvard", "mla", "chicago", "ieee", "vancouver", "oscola", "turabian")
CURRENCY_MARKS = {"USD": ("usd", "$", "dollar"), "EUR": ("eur", "€", "euro"), "GBP": ("gbp", "£", "pound"), "UGX": ("ugx", "shilling"), "KES": ("kes", "shilling")}


def _figures(text: str) -> list[tuple[float, int]]:
    """Every number a quote states, each read whole with its scale, with where it ends: in figures
    ("1,500", "50k", "1.5 million") or in words ("two thousand five hundred")."""
    found: list[tuple[float, int]] = []
    for m in FIGURE.finditer(text):
        value = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        found.append((value * SCALES[m.group(3).lower()] if m.group(3) else value, m.end()))
    total, part, last = 0.0, 0.0, 0
    for m in WORD.finditer(text.casefold()):
        word = m.group(0)
        if word in NUMBER_WORDS:
            part, last = part + NUMBER_WORDS[word], m.end()
        elif word == "hundred" and part:
            part, last = part * 100, m.end()
        elif word in ("thousand", "million", "billion") and part:
            total, part, last = total + part * SCALES[word], 0.0, m.end()
        elif word != "and" and (total or part):
            found.append((total + part, last))
            total, part = 0.0, 0.0
    if total or part:
        found.append((total + part, last))
    return found


def _numbers_in(text: str) -> set[float]:
    return {value for value, _ in _figures(text)}


def value_in_quote(key: str, value: str, number: float | None, quote: str) -> bool:
    """The extracted value agrees with its own quote (Codex audit 2026-09-30 #10, second round): its
    number is stated there whole, with its scale ("USD 50k" is never 50); a limit's number is the one
    next to its unit ("a 5-page limit" is never 50 pages, even beside "50 applicants"); a duration in
    months may be stated in years; a referencing style and a currency are named. Anything else is
    shown to the student to confirm."""
    words = quote.casefold()
    if number is not None:
        figures = _figures(quote)
        if key in UNIT_WORDS:
            units = UNIT_WORDS[key]
            if not any(v == number and any(u in words[end : end + UNIT_GAP] for u in units) for v, end in figures):
                return False
        elif key == "duration_months":
            if not any(v == number or (v == number / 12 and "year" in words[end : end + UNIT_GAP]) for v, end in figures):
                return False
        elif number not in {v for v, _ in figures}:
            return False
    elif key in UNIT_WORDS and not any(u in words for u in UNIT_WORDS[key]):
        return False
    if key == "citation_style":
        named = [s for s in STYLE_WORDS if s in value.casefold().replace(" ", "")]
        if named and not any(s in words for s in named):
            return False
    if key == "currency":
        marks = CURRENCY_MARKS.get(value.strip().upper()[:3])
        if marks and not any(m in words for m in marks):
            return False
    return True


def requirements_from(answer: dict[str, Any], sources: list[SourceFile], texts: dict[str, str]) -> tuple[list[Requirement], list[str]]:
    """The reader's answer as requirements, each checked against its own source's text. A quote
    that cannot be found is kept but unverified: the student confirms it or it is not used."""
    by_id = {s.id: s for s in sources}
    out: list[Requirement] = []
    seen: set[tuple[str, str, str]] = set()
    for item in answer.get("requirements", [])[:250]:
        source = by_id.get(item.get("sourceId", ""))
        key = item.get("key", "")
        if source is None or key not in KEYS:
            continue
        value = " ".join(str(item.get("value", "")).split())[:600]
        quote = " ".join(str(item.get("quote", "")).split())[:800]
        fingerprint = (key, value.casefold(), source.id)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        label, high = KEYS[key]
        number = item.get("number")
        number = float(number) if isinstance(number, int | float) else None
        out.append(
            Requirement(
                id=f"R{secrets.token_hex(4)}",
                key=key,
                label=label,
                value=value,
                number=number,
                unit=str(item.get("unit", ""))[:40],
                hard=bool(item.get("hard", True)),
                authority="EXTERNAL_MANDATORY" if item.get("hard", True) else "QUALITY_GUIDANCE",
                source=source.name,
                source_id=source.id,
                quote=quote,
                location=str(item.get("location", ""))[:200],
                verified=quote_found(quote, texts.get(source.id, "")) and value_in_quote(key, value, number, quote),
                high_stakes=high,
                weight=float(item["weight"]) if isinstance(item.get("weight"), int | float) else None,
                counts_toward=[str(c)[:40] for c in item.get("countsToward", [])][:10],
                amends=bool(item.get("amends", False)),
            )
        )
    unclear = [" ".join(str(u).split())[:300] for u in answer.get("unclear", [])][:20]
    return out, unclear

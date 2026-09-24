"""University guide → FormattingSpec.

The models negotiate the rules (see app/ai/orchestration.py); this module defines the shape they
exchange, turns their answer into a safe FormattingSpec (every value bounded, out-of-range values
clamped and reported), and provides a deterministic reader that independently detects
contradictions in a guide, so a model's answer cannot hide one.
"""

import re
from typing import Any

from app.formatting.presets import FormattingSpec, HeadingStyle
from app.jobs.models import RuleEvidence

PAGE_NUMBERS = ["top-right", "top-center", "bottom-center", "bottom-right"]
MAX_GUIDE_WORDS = 15_000  # longer guides are refused at upload, so every model step sees the whole guide

_NUMBER = {"type": "number"}
_HEADING = {
    "type": "object",
    "properties": {"size_pt": _NUMBER, "bold": {"type": "boolean"}, "italic": {"type": "boolean"}, "align": {"type": "string", "enum": ["left", "center"]}},
    "required": ["size_pt", "bold", "italic", "align"],
    "additionalProperties": False,
}
SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "margins_cm": {
            "type": "object",
            "properties": {"top": _NUMBER, "bottom": _NUMBER, "left": _NUMBER, "right": _NUMBER},
            "required": ["top", "bottom", "left", "right"],
            "additionalProperties": False,
        },
        "font": {"type": "string"},
        "size_pt": _NUMBER,
        "line_spacing": _NUMBER,
        "first_line_indent_cm": _NUMBER,
        "space_after_pt": _NUMBER,
        "alignment": {"type": "string", "enum": ["left", "justify"]},
        "paper_size": {"type": "string", "enum": ["A4", "Letter"]},
        "heading1": _HEADING,
        "heading2": _HEADING,
        "heading3": _HEADING,
        "page_numbers": {"type": "string", "enum": PAGE_NUMBERS},
        "roman_preliminary_pages": {"type": "boolean"},
        "references_hanging_cm": _NUMBER,
        "references_line_spacing": _NUMBER,
        "insert_toc": {"type": "boolean"},
        "evidence": {
            "type": "array",
            "items": {"type": "object", "properties": {"rule": {"type": "string"}, "quote": {"type": "string"}}, "required": ["rule", "quote"], "additionalProperties": False},
        },
        "conflicts": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        # Rules in the guide this schema cannot express (captions, title pages, ...): never dropped
        # silently — each becomes a warning and the job is marked PARTIAL.
        "unsupported": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "margins_cm", "font", "size_pt", "line_spacing", "first_line_indent_cm", "space_after_pt", "alignment", "paper_size", "heading1",
        "heading2", "heading3", "page_numbers", "roman_preliminary_pages", "references_hanging_cm", "references_line_spacing", "insert_toc",
        "evidence", "conflicts", "assumptions", "unsupported",
    ],
    "additionalProperties": False,
}

# Plausible ranges; anything outside is clamped and reported rather than applied blindly.
_BOUNDS = {
    "margin": (1.0, 5.0),
    "size_pt": (9.0, 16.0),
    "line_spacing": (1.0, 3.0),
    "first_line_indent_cm": (0.0, 2.5),
    "space_after_pt": (0.0, 24.0),
    "heading_size": (9.0, 20.0),
    "references_hanging_cm": (0.0, 2.5),
}


def _normal(text: str) -> str:
    """Lowercase letters and digits only, so a quote matches despite curly quotes, dashes or wrapping."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def to_spec(data: dict[str, Any], label: str, guide: str) -> tuple[FormattingSpec, list[RuleEvidence], list[str], list[str]]:
    """Validated model answer → (FormattingSpec, evidence, notes, checks).

    Notes carry conflicts, assumptions and values clamped into a sensible range. Checks are rules
    the student must verify themselves — rules we cannot apply, or whose quoted source is not in
    the guide — and make the job PARTIAL. Contradictions are found independently of the models too,
    so a final answer that leaves one out cannot hide it."""
    conflicts = list(data.get("conflicts", []))
    if not any("spac" in c.lower() for c in conflicts):  # the deterministic reader detects spacing conflicts
        conflicts += read_guide(guide)["conflicts"]
    notes = [f"Your guide is contradictory: {c}" for c in conflicts]
    notes += [f"Your guide doesn't say, so we assumed: {a}" for a in data.get("assumptions", [])]
    checks = [f"Not applied automatically — please apply it yourself: {u}" for u in data.get("unsupported", [])]

    def bounded(name: str, value: float, bounds: str) -> float:
        low, high = _BOUNDS[bounds]
        clamped = min(high, max(low, float(value)))
        if clamped != float(value):
            notes.append(f"{name} of {value:g} is outside the usual range, so we used {clamped:g}.")
        return clamped

    m = data["margins_cm"]
    headings = {}
    for level in (1, 2, 3):
        h = data[f"heading{level}"]
        headings[level] = HeadingStyle(size_pt=bounded(f"Heading {level} size", h["size_pt"], "heading_size"), bold=h["bold"], italic=h["italic"], align=h["align"])
    spec = FormattingSpec(
        id="template",
        label=label,
        margins_cm=tuple(bounded(f"{side.capitalize()} margin", m[side], "margin") for side in ("top", "bottom", "left", "right")),  # type: ignore[arg-type]
        font=(data.get("font") or "Times New Roman").strip()[:60],
        size_pt=bounded("Font size", data["size_pt"], "size_pt"),
        line_spacing=bounded("Line spacing", data["line_spacing"], "line_spacing"),
        first_line_indent_cm=bounded("First-line indent", data["first_line_indent_cm"], "first_line_indent_cm"),
        space_after_pt=bounded("Paragraph spacing", data["space_after_pt"], "space_after_pt"),
        alignment=data["alignment"],
        headings=headings,
        heading_space_before_pt=12,
        heading_space_after_pt=6,
        page_numbers=data["page_numbers"],
        roman_preliminary_pages=data["roman_preliminary_pages"],
        references_hanging_cm=bounded("Reference hanging indent", data["references_hanging_cm"], "references_hanging_cm"),
        references_line_spacing=bounded("Reference line spacing", data["references_line_spacing"], "line_spacing"),
        insert_toc=data["insert_toc"],
        paper_size=data["paper_size"],
    )
    source = _normal(guide)
    evidence = []
    for e in data.get("evidence", [])[:30]:
        quote = _normal(e["quote"])
        if quote and quote in source:
            evidence.append(RuleEvidence(rule=e["rule"][:80], quote=e["quote"][:240]))
        else:
            checks.append(f"Check this rule yourself: {e['rule'][:80]} — we couldn't find where your guide says this.")
    return spec, evidence, notes, checks


# --- deterministic reader -------------------------------------------------------

_FONTS = r"(Times New Roman|Arial|Calibri|Cambria|Garamond|Georgia|Book Antiqua|Century Gothic|Helvetica|Verdana)"


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _cm(value: str, unit: str) -> float:
    number = float(value)
    return round(number * 2.54, 2) if unit.lower().startswith(("in", '"')) else number


def read_guide(text: str) -> dict[str, Any]:
    """Best-effort rule extraction in the same shape the lead model returns."""
    sentences = _sentences(text)
    evidence: list[dict[str, str]] = []
    conflicts: list[str] = []
    assumptions: list[str] = []

    def find(pattern: str) -> tuple[re.Match[str], str] | None:
        for s in sentences:
            match = re.search(pattern, s, re.I)
            if match:
                return match, s
        return None

    def cite(rule: str, sentence: str) -> None:
        evidence.append({"rule": rule, "quote": sentence[:200]})

    font = "Times New Roman"
    if hit := find(_FONTS):
        font = hit[0].group(1)
        cite(f"Font: {font}", hit[1])
    else:
        assumptions.append("Times New Roman for body text")

    size = 12.0
    for s in sentences:  # body size: "font size 12" or "12 pt", never a heading rule or "paper size A4"
        if re.search(r"heading", s, re.I):
            continue
        m = re.search(r"font\s*size\D{0,6}(\d{1,2}(?:\.\d)?)|\b(\d{1,2}(?:\.\d)?)\s*(?:pt|point)\b", s, re.I)
        if m and 8 <= float(m.group(1) or m.group(2)) <= 16:
            size = float(m.group(1) or m.group(2))
            cite(f"Font size: {size:g} pt", s)
            break

    spacings: list[tuple[float, str]] = []
    for s in sentences:
        low = s.lower()
        if "spac" not in low:
            continue
        if re.search(r"double", low):
            spacings.append((2.0, s))
        elif re.search(r"1\.5|one and a half", low):
            spacings.append((1.5, s))
        elif re.search(r"single", low) and not re.search(r"quotation|reference|block", low):
            spacings.append((1.0, s))
    line_spacing = spacings[0][0] if spacings else 1.5
    if spacings:
        cite(f"Line spacing: {line_spacing:g}", spacings[0][1])
        others = sorted({v for v, _ in spacings if v != line_spacing})
        if others:
            conflicts.append(
                f"it gives line spacing {line_spacing:g} in one place and {', '.join(f'{v:g}' for v in others)} in another. Check which your department wants."
            )
    else:
        assumptions.append("1.5 line spacing")

    margins = {"top": 2.54, "bottom": 2.54, "left": 2.54, "right": 2.54}
    margin_sentences = [s for s in sentences if "margin" in s.lower()]
    for s in margin_sentences:
        parts = re.split(r";|\band\s+(?=\d)", s)
        for part in parts:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(cm|centimet\w*|inch\w*|\")", part, re.I)
            if not m:
                continue
            value = _cm(m.group(1), m.group(2))
            sides = [side for side in margins if re.search(rf"\b{side}\b", part, re.I)] or list(margins)
            for side in sides:
                margins[side] = value
        cite("Margins", s)
    if not margin_sentences:
        assumptions.append("2.54 cm margins on all sides")

    page_numbers = "bottom-center"
    if hit := find(r"page number"):
        low = hit[1].lower()
        vertical = "top" if "top" in low else "bottom"
        horizontal = "right" if "right" in low else "center"
        page_numbers = f"{vertical}-{horizontal}"
        cite(f"Page numbers: {page_numbers}", hit[1])

    roman_hit = find(r"roman numeral")
    roman = roman_hit is not None
    if roman_hit:
        cite("Preliminary pages in Roman numerals", roman_hit[1])

    hanging = 1.27
    if hit := find(r"hanging indent\D{0,12}(\d+(?:\.\d+)?)\s*(cm|inch\w*)"):
        hanging = _cm(hit[0].group(1), hit[0].group(2))
        cite(f"Reference hanging indent: {hanging:g} cm", hit[1])

    heading1 = {"size_pt": size + 2, "bold": True, "italic": False, "align": "center"}
    if hit := find(r"(?:chapter|main)?\s*heading\w*\D{0,30}(\d{1,2})\s*(?:pt|point)"):
        heading1["size_pt"] = float(hit[0].group(1))
        heading1["align"] = "center" if re.search(r"cent(re|er)", hit[1], re.I) else "left"
        cite("Chapter headings", hit[1])

    paper_size = "A4"
    if hit := find(r"\bletter\b.{0,20}\b(paper|size)\b|\b(paper|page) size\b.{0,20}\bletter\b|8\.5\s*(x|×|by)\s*11"):
        paper_size = "Letter"
        cite("Paper size: Letter", hit[1])
    elif hit := find(r"\bA4\b"):
        cite("Paper size: A4", hit[1])

    justify = bool(find(r"justif"))
    if justify:
        cite("Justified text", find(r"justif")[1])  # type: ignore[index]
    # Any other instruction ("shall", "must", ...) is something this reader did not apply: report it.
    used = {e["quote"] for e in evidence} | {sentence[:200] for _, sentence in spacings}
    unsupported = [
        sentence[:200]
        for sentence in sentences
        if sentence[:200] not in used and re.search(r"\b(shall|must|should|required|are to|is to)\b", sentence, re.I)
    ]
    return {
        "margins_cm": margins,
        "font": font,
        "size_pt": size,
        "line_spacing": line_spacing,
        "first_line_indent_cm": 0.0 if justify else 1.27,
        "space_after_pt": 6.0 if justify else 0.0,
        "alignment": "justify" if justify else "left",
        "paper_size": paper_size,
        "heading1": heading1,
        "heading2": {"size_pt": size, "bold": True, "italic": False, "align": "left"},
        "heading3": {"size_pt": size, "bold": True, "italic": True, "align": "left"},
        "page_numbers": page_numbers,
        "roman_preliminary_pages": roman,
        "references_hanging_cm": hanging,
        "references_line_spacing": 1.0 if find(r"references?\b.*single") else line_spacing,
        "insert_toc": bool(find(r"table of contents")),
        "evidence": evidence,
        "conflicts": conflicts,
        "assumptions": assumptions,
        "unsupported": unsupported,
    }

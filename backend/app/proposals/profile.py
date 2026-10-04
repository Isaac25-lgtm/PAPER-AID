"""Institution profiles from an uploaded research guide (Proposal V2). The lead model drafts the
profile from the guide, the writer critiques it and the lead finalises it (the permanent loop);
code then validates it into a rulebook of the same shape as the UCU one, filling what the guide
does not cover from that default and saying so. A profile is data: its chapters, sections, rules
and checklist steer the proposal exactly as the default rulebook does."""

import copy
import math
import re
import secrets
from typing import Any

from app.proposals import rulebook

_S = {"type": "string"}
_N = {"type": "number"}
_I = {"type": "integer"}
_B = {"type": "boolean"}
LEVELS = ("BACHELORS", "PGD", "MASTERS", "PHD")


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


SECTION = _obj({"key": _S, "heading": _S, "brief": _S, "share": _N, "perObjective": _B, "table": _B})
SCHEMA = _obj(
    {
        "institution": _S,
        "short": _S,
        "citation": {"type": "string", "enum": ["APA6", "APA7", "OTHER"]},
        "chapters": _list(_obj({"number": _I, "title": _S, "purpose": _S, "share": _N, "sections": _list(SECTION)})),
        "levels": _list(_obj({"level": {"type": "string", "enum": list(LEVELS)}, "pagesMin": _I, "pagesMax": _I})),
        "objectives": _obj({"min": _I, "max": _I}),
        "formatting": _obj({"font": _S, "sizePt": _N, "lineSpacing": _N, "marginsIn": _N}),
        "rules": _list(_S),
        "vetting": _list(_obj({"chapter": _I, "question": _S})),
        "unclear": _list(_S),
    }
)
CRITIQUE_SCHEMA = _obj({"items": _list(_obj({"field": _S, "problem": _S, "proposal": _S})), "overall": _S})


class NotAGuide(ValueError):
    """The finalised profile cannot be used (no usable structure): the step fails without charge."""


def reference() -> dict[str, Any]:
    """What the models see of the default: its structure, and what each known key means."""
    book = rulebook.load(rulebook.DEFAULT)
    chapters = [c for c in book["chapters"] if c.get("kind") != "CONCEPT"]
    structure = [
        {"number": c["number"], "title": c["title"], "share": c["share"], "sections": [{"key": s["key"], "heading": s["heading"], "share": s["share"]} for s in c["sections"]]}
        for c in chapters
    ]
    known = {f"{c['number']}:{s['key']}": s["brief"] for c in chapters for s in c["sections"]}
    return {"structure": structure, "knownKeys": known}


def _num(value: Any) -> float:
    """A finite number from a model value, or 0 when it is not one (Codex audit 56c4f83 M16)."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    try:
        number = float(value)
    except (ValueError, OverflowError):  # not a number, or too large to be one (Codex re-check M16)
        return 0.0
    return number if math.isfinite(number) else 0.0


def _text(value: Any) -> str:
    """A model value as text: only strings count (a null, list or number is empty)."""
    return value.strip() if isinstance(value, str) else ""


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    return [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def _key(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())[:24] or "section"


def _normalised(values: list[float]) -> list[float]:
    positive = [max(0.0, v) for v in values]
    total = sum(positive)
    return [v / total for v in positive] if total > 0 else [1 / len(values)] * len(values)


def build(answer: dict[str, Any], guide_name: str) -> dict[str, Any]:
    """A rulebook from the finalised profile. Structure that cannot be used is refused (NotAGuide);
    values the guide did not give come from the default and are listed in `unclear`."""
    default = rulebook.load(rulebook.DEFAULT)
    if not isinstance(answer, dict):
        raise NotAGuide("the profile is not an object")
    chapters_in = {c["number"]: c for c in _dicts(answer.get("chapters")) if type(c.get("number")) is int}
    if sorted(chapters_in, key=str) != [1, 2, 3] or any(len(_dicts(c.get("sections"))) < 2 for c in chapters_in.values()):
        raise NotAGuide("the profile needs chapters 1-3 with at least two sections each")
    unclear = _texts(answer.get("unclear"))[:20]
    source = f"{_text(answer.get('institution')) or 'Institution'} research guide ({guide_name[:80]})"

    shares = _normalised([_num(chapters_in[n].get("share")) for n in (1, 2, 3)])
    chapters = []
    for n, share in zip((1, 2, 3), shares, strict=True):
        spec = chapters_in[n]
        raw = _dicts(spec["sections"])[:20]
        section_shares = _normalised([_num(s.get("share")) for s in raw])
        seen: set[str] = set()
        sections = []
        per_objective_used = False
        for s, s_share in zip(raw, section_shares, strict=True):
            key = _key(_text(s.get("key")) or _text(s.get("heading")))
            while key in seen:
                key += "x"
            seen.add(key)
            section = {"key": key, "heading": _text(s.get("heading"))[:120] or key.title(), "brief": _text(s.get("brief"))[:400], "share": round(s_share, 4), "source": source}
            if s.get("perObjective") and n == 2 and not per_objective_used:
                section["per_objective"], per_objective_used = True, True
            if s.get("table"):
                section["table"] = True
            sections.append(section)
        chapters.append({"number": n, "title": _text(spec.get("title"))[:120] or default["chapters"][n - 1]["title"], "share": round(share, 4),
                         "purpose": _text(spec.get("purpose"))[:300], "source": source, "sections": sections})
    chapters.append(copy.deepcopy(next(c for c in default["chapters"] if c.get("kind") == "CONCEPT")))  # the concept paper keeps the default layout

    levels = copy.deepcopy(default["levels"])
    given = {_text(entry.get("level")): entry for entry in _dicts(answer.get("levels"))}
    for level in LEVELS:
        entry = given.get(level)
        low, high = (int(_num(entry.get("pagesMin"))), int(_num(entry.get("pagesMax")))) if entry else (0, 0)
        if 0 < low <= high <= 200:
            levels[level] = {"label": levels[level]["label"], "pages": [low, high], "source": source}
    if not given:
        unclear.append("The guide gives no page range for a proposal, so a typical length is used.")

    objectives = answer.get("objectives") if isinstance(answer.get("objectives"), dict) else {}
    low, high = int(_num(objectives.get("min"))), int(_num(objectives.get("max")))
    counts = {"min": low, "max": high, "source": source} if 0 < low <= high <= 10 else dict(default["objectives"])

    fmt = answer.get("formatting") if isinstance(answer.get("formatting"), dict) else {}
    formatting = dict(default["formatting"])
    if isinstance(fmt.get("font"), str) and fmt["font"].strip():
        formatting["font"] = fmt["font"].strip()[:60]
    if 9 <= _num(fmt.get("sizePt")) <= 16:
        formatting["size_pt"] = _num(fmt["sizePt"])
    if 1 <= _num(fmt.get("lineSpacing")) <= 3:
        formatting["line_spacing"] = _num(fmt["lineSpacing"])
    if 0.5 <= _num(fmt.get("marginsIn")) <= 2:
        formatting["margins_in"] = _num(fmt["marginsIn"])
    formatting["source"] = source

    rules = [
        {"id": f"G-{i}", "requirement": str(r).strip()[:400], "interpretation": "", "enforcement": "REQUIRED", "type": "ai", "source": source}
        for i, r in enumerate(_texts(answer.get("rules"))[:25], start=1)
    ]
    questions: dict[str, list[dict[str, str]]] = {"1": [], "2": [], "3": []}
    for i, q in enumerate(_dicts(answer.get("vetting")), start=1):
        if str(q.get("chapter")) in questions and isinstance(q.get("question"), str) and q["question"].strip():
            questions[str(q["chapter"])].append({"id": f"C{q['chapter']}-G{i}", "question": str(q["question"]).strip()[:300]})
    for n, qs in questions.items():
        if not qs:  # no criteria for this chapter in the guide: general proposal questions
            questions[n] = copy.deepcopy(default["vetting"]["questions"][n])
    questions["4"] = copy.deepcopy(default["vetting"]["questions"]["4"])

    citation = answer.get("citation")
    if citation == "OTHER":
        unclear.append("The guide asks for a citation style PaperAid does not produce; APA 7 is used.")
    default_citation = "APA6" if citation == "APA6" else "APA7"
    return {
        "id": f"custom-{secrets.token_hex(6)}",
        "institution": _text(answer.get("institution"))[:160] or "Your institution",
        "short": _text(answer.get("short"))[:20],
        "source": source,
        "source_sha256": "",
        "note": "Built by PaperAid from the student's uploaded guide; values the guide does not give come from the default profile.",
        "custom": True,
        "unclear": list(dict.fromkeys(unclear)),
        "citation_profiles": {"APA6": {"label": "APA 6th edition", "source": source}, "APA7": {"label": "APA 7th edition", "source": source}},
        "default_citation": default_citation,
        "levels": levels,
        "words_per_page": default["words_per_page"],
        "words_per_page_source": default["words_per_page_source"],
        "objectives": counts,
        "questions": counts,
        "citation_style": {"style": "APA", "source": source},
        "formatting": formatting,
        "preliminary_pages": default["preliminary_pages"],
        "rules": rules or copy.deepcopy(default["rules"]),
        "chapters": chapters,
        "vetting": {"source": source, "note": "", "questions": questions},
    } | {"departures": departures({"chapters": chapters, "objectives": counts, "levels": levels, "formatting": formatting})}


# --- where a guide departs a lot from the standard guide (owner decision 2026-10-04) ------------------------------
# Each is put to the student, who confirms it ("as my guide says") or takes the standard guide's version instead.
# The sections a proposal normally can't do without: (chapter, the standard guide's key, words that find it in a heading)
CORE = [(1, "problem", ("problem",)), (1, "objectives", ("objective",)), (2, "empirical", ("literature", "review", "empirical", "related stud")),
        (3, "sampling", ("sampl",)), (3, "instruments", ("instrument", "data collection", "tool")), (3, "analysis", ("analys",)), (3, "ethics", ("ethic",))]
CHAPTER_WORDS = {1: "One", 2: "Two", 3: "Three"}


def departures(book: dict[str, Any]) -> list[dict[str, str]]:
    default = rulebook.load(rulebook.DEFAULT)
    out = []
    by_number = {c["number"]: c for c in book["chapters"]}
    for number, key, words in CORE:
        chapter = by_number.get(number)
        text = " ".join([chapter["title"], *(s["heading"] for s in chapter["sections"])]).lower() if chapter else ""
        if not any(w in text for w in words):
            standard = next(s for s in default["chapters"][number - 1]["sections"] if s["key"] == key)
            out.append({"id": f"section:{number}:{key}", "question": f"Your guide has no \"{standard['heading']}\" section in Chapter {CHAPTER_WORDS[number]}. Leave it out?",
                        "keep": "Leave it out, as my guide says", "standard": f"Add \"{standard['heading']}\" as the standard guide has it"})
    low, high = int(book["objectives"]["min"]), int(book["objectives"]["max"])
    if high < 2 or low > 6:
        d = default["objectives"]
        out.append({"id": "objectives", "question": f"Your guide asks for {low} to {high} specific objectives (the standard guide: {d['min']} to {d['max']}). Is that right?",
                    "keep": "Yes, as my guide says", "standard": f"Use {d['min']} to {d['max']}, as the standard guide has it"})
    for level, entry in book["levels"].items():
        lo, hi = entry["pages"]
        dlo, dhi = default["levels"][level]["pages"]
        if hi < dlo / 2 or lo > dhi * 2:
            out.append({"id": f"pages:{level}", "question": f"Your guide asks for {lo} to {hi} pages for a {entry['label']} proposal (the standard guide: {dlo} to {dhi}). "
                        "Is that right?", "keep": "Yes, as my guide says", "standard": f"Use {dlo} to {dhi} pages, as the standard guide has it"})
    fmt = book["formatting"]
    if not 10 <= float(fmt.get("size_pt", 12)) <= 14 or not 1 <= float(fmt.get("line_spacing", 1.5)) <= 2.5:
        d = default["formatting"]
        out.append({"id": "formatting", "question": f"Your guide asks for {fmt.get('size_pt')} pt text with {fmt.get('line_spacing')} line spacing, which is unusual. Is that right?",
                    "keep": "Yes, as my guide says", "standard": f"Use {d['size_pt']:g} pt and {d['line_spacing']:g} spacing, as the standard guide has it"})
    return out


def with_standard(book: dict[str, Any], departure_id: str) -> dict[str, Any]:
    """A new profile (profiles never change once saved) taking the standard guide's version of one point."""
    default = rulebook.load(rulebook.DEFAULT)
    new = copy.deepcopy(book)
    new["id"] = f"custom-{secrets.token_hex(6)}"
    new["based_on"] = book["id"]
    kind, _, rest = departure_id.partition(":")
    if kind == "section":
        number, key = rest.split(":")
        standard = copy.deepcopy(next(s for s in default["chapters"][int(number) - 1]["sections"] if s["key"] == key))
        chapter = next(c for c in new["chapters"] if c["number"] == int(number))
        share = float(standard.get("share", 0.05))
        total = sum(float(s["share"]) for s in chapter["sections"]) or 1.0
        for s in chapter["sections"]:  # the others keep their proportions and leave room for it
            s["share"] = round(float(s["share"]) * (1 - share) / total, 4)
        while any(s["key"] == standard["key"] for s in chapter["sections"]):
            standard["key"] += "x"
        chapter["sections"].append(standard | {"share": round(share, 4), "source": "the standard guide (the student chose it)"})
    elif kind == "objectives":
        new["objectives"] = new["questions"] = copy.deepcopy(default["objectives"])
    elif kind == "pages":
        new["levels"][rest] = copy.deepcopy(default["levels"][rest])
    elif kind == "formatting":
        new["formatting"] = copy.deepcopy(default["formatting"])
    else:
        raise ValueError(f"unknown departure {departure_id}")
    new["departures"] = departures(new)
    return new

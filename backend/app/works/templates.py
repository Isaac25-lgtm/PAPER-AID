"""The plan skeleton for a work, from its variant's template (rule data) and its resolved
specification: section words scaled to the target, conditional sections included only when they
apply, form fields planned box by box, an official template's headings kept in their order, and
published scoring weights shaping depth without becoming word shares (rulebook §16, SH-008)."""

import math
import re

from app.rules import library
from app.works.models import PlanSection, ResolvedSpec

# Words a criterion's name must share with a section before the criterion shapes that section.
CRITERION_WORDS: dict[str, tuple[str, ...]] = {
    "relevance": ("relevance", "relevant", "fit", "priorit", "alignment", "strategic"),
    "problem": ("need", "problem", "situation", "context", "justification"),
    "approach": ("approach", "technical", "method", "design", "strategy", "quality", "activities"),
    "technical_approach": ("approach", "technical", "method", "design", "strategy", "quality"),
    "capacity": ("capacity", "experience", "organisation", "organization", "team", "management", "track", "applicant", "expertise"),
    "sustainability": ("sustainab", "exit", "continu", "scale", "ownership"),
    "sustainability_risk": ("sustainab", "risk", "continu"),
    "mel": ("monitor", "evaluat", "learning", "mel", "m&e", "measurement", "results framework"),
    "budget_narrative": ("budget", "cost", "value for money", "efficien", "financial"),
    "timeline_budget": ("budget", "cost", "timeline", "financial"),
    "innovation": ("innovat", "novel", "originality", "contribution"),
    "expected_results": ("impact", "result", "outcome", "effectiveness"),
    "results": ("impact", "result", "outcome"),
    "risks": ("risk",),
    "partnerships": ("partner", "consortium", "collaborat"),
    "significance": ("significance", "importance", "impact"),
    "methods": ("method", "rigour", "rigor", "design"),
    "feasibility": ("feasib", "deliverab"),
}
MAX_THEMES = 6


def _themes(words: int) -> int:
    return 2 if words <= 1200 else 3 if words <= 2600 else 4 if words <= 4500 else 5 if words <= 7000 else MAX_THEMES


def _included(section: dict, spec: ResolvedSpec) -> bool:
    condition = section.get("conditional")
    if section.get("required", True) or not condition:
        return True
    if condition == "budget_or_timeline":
        return spec.flags.get("budget_required", False) or spec.flags.get("timeline_required", False)
    if condition == "postgraduate":
        return spec.level == "POSTGRADUATE"
    return bool(spec.flags.get(condition, False))


def _template_sections(spec: ResolvedSpec) -> list[dict]:
    variant = library.book(spec.kind)["variants"][spec.variant]
    if "mode_sections" in variant:
        return variant["mode_sections"].get(spec.mode or "STANDARD") or variant["mode_sections"]["STANDARD"]
    return variant["sections"]


def skeleton(spec: ResolvedSpec) -> list[PlanSection]:
    """Sections with their words, before the writer names themes and writes each brief."""
    if spec.fields:  # an online form: planned box by box, never cut out of a long narrative (Appendix B3)
        return [
            PlanSection(key=f"field_{f.id}", heading=f.label[:200], words=int(f.max_words or (f.max_characters or 600) / 6.8), min_words=0,
                        max_words=int(f.max_words or (f.max_characters or 600) / 5.5), required=f.required, locked=True, field_id=f.id)
            for f in spec.fields
        ]
    rows = [s for s in _template_sections(spec) if _included(s, spec)]
    target = spec.target_words
    sections: list[PlanSection] = []
    if rows and "share" in rows[0]:  # coursework: shares of the target, the body split into themes
        total = sum(r["share"] for r in rows)
        for r in rows:
            words = round(target * r["share"] / total)
            if r.get("body"):
                n = _themes(words)
                each = max(150, round(words / n))
                sections += [PlanSection(key=f"theme{i}", heading=f"Theme {i}", words=each, min_words=round(each * 0.7), max_words=round(each * 1.3), brief=r["purpose"])
                             for i in range(1, n + 1)]
                continue
            sections.append(PlanSection(key=r["key"], heading=r["heading"], words=words, min_words=round(words * 0.7), max_words=round(words * 1.5), required=r.get("required", True), brief=r["purpose"]))
    else:  # concept notes and funding proposals: the template's words, scaled to the target
        base = sum(r["words"] for r in rows) or 1
        factor = target / base
        for r in rows:
            words = round(r["words"] * factor)
            sections.append(PlanSection(key=r["key"], heading=r["heading"], words=words, min_words=round(r["min"] * factor), max_words=round(r["max"] * factor),
                                        required=r.get("required", True), brief=r["purpose"]))
    if spec.template_headings:
        sections = _follow_template(sections, spec.template_headings, target)
    sections = _name_required(sections, [r.value for r in spec.requirements if r.key == "section.required"], target)
    return rebalance(sections, spec)


# Words calls use for parts PaperAid's templates name differently.
SAME_PART = {
    "intervention": {"approach", "activities", "solution", "strategy"}, "proposed": {"approach"}, "implementation": {"management", "timeline", "workplan", "delivery"},
    "arrangements": {"management", "implementation"}, "results": {"outcomes", "outputs", "impact"}, "budget": {"cost", "costs", "financial"},
    "applicant": {"organisation", "organization", "capacity", "experience"}, "organisation": {"applicant", "capacity"}, "problem": {"need", "needs", "context"},
    "monitoring": {"mel", "evaluation", "learning"}, "sustainability": {"exit", "continuity"}, "beneficiaries": {"target", "group"},
    "workplan": {"timeline", "schedule", "implementation"}, "work": {"timeline"}, "timeline": {"workplan", "schedule"}, "schedule": {"timeline", "workplan"},
}


def _name_required(sections: list[PlanSection], required: list[str], target: int) -> list[PlanSection]:
    """Each section the call requires by name gets a heading with that name, locked: a section whose
    heading already has it keeps it; otherwise the section that covers it is renamed (the same words
    first, then usual equivalents: a call's "intervention" is PaperAid's "approach"), carrying both
    names when it already carries one; failing that, a section is added (real-model pilot 2026-09-30:
    "Proposed intervention" was written under "Approach" and the draft failed the required check)."""
    out = list(sections)
    names = [n for n in dict.fromkeys(" ".join(r.split()) for r in required if r.strip()) if _words_of(n)]
    carried: dict[int, list[str]] = {}  # section → the required names its heading must carry
    left = []
    for name in names:
        index = next((n for n, s in enumerate(out) if _words_of(name) <= _words_of(s.heading)), None)
        if index is None:
            left.append(name)
        else:
            carried.setdefault(index, []).append(name)
    kept = set(carried)  # headings that already name what the call asks: kept as written unless more is added
    template_locked = {n for n, s in enumerate(sections) if s.locked}
    for loose in (False, True):
        for name in list(left):
            words = _words_of(name)
            wanted = words.union(*(SAME_PART.get(w, set()) for w in words)) if loose else words
            scored = [(len(wanted & _words_of(sections[n].heading + " " + s.key.replace("_", " "))), n) for n, s in enumerate(out) if n not in template_locked]
            score, index = max(scored, default=(0, -1))
            if score > 0:
                carried.setdefault(index, []).append(name)
                kept.discard(index)
                left.remove(name)
    for index, carried_names in carried.items():
        heading = out[index].heading if index in kept else " and ".join(carried_names)
        out[index] = out[index].model_copy(update={"heading": (heading[0].upper() + heading[1:])[:200], "locked": True, "required": True})
    for name in left:
        heading = (name[0].upper() + name[1:])[:200]
        each = max(100, round(target / max(1, len(out) + 1)))
        out.append(PlanSection(key=f"required{len(out) + 1}", heading=heading, words=each, min_words=round(each * 0.6), max_words=round(each * 1.5),
                               locked=True, brief=f"What the call asks for under \"{heading}\"."))
    if not left:
        return out
    total = sum(s.words for s in out) or 1
    return [s.model_copy(update={"words": round(s.words * target / total), "min_words": round(s.min_words * target / total), "max_words": round(s.max_words * target / total)}) for s in out]


STOP = {"and", "the", "of", "for", "to", "in", "a", "an", "on", "with", "your", "its", "their"}


def _words_of(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower())) - STOP


def _follow_template(sections: list[PlanSection], headings: list[str], target: int) -> list[PlanSection]:
    """An official template's headings, in its order and locked; each keeps the key (and so the
    rules) of the PaperAid section it matches best, and its words; a heading with no match gets an
    even share. The total is then scaled back to the target."""
    out: list[PlanSection] = []
    used: set[str] = set()
    for n, heading in enumerate(headings, start=1):
        words = _words_of(heading)
        scored = [(len(words & _words_of(s.heading + " " + s.key.replace("_", " "))), s) for s in sections if s.key not in used]
        score, match = max(scored, key=lambda t: t[0], default=(0, None))
        if match is not None and score > 0:
            used.add(match.key)
            out.append(match.model_copy(update={"heading": heading[:200], "locked": True, "required": True}))
        else:
            each = max(100, round(target / max(1, len(headings))))
            out.append(PlanSection(key=f"template{n}", heading=heading[:200], words=each, min_words=round(each * 0.6), max_words=round(each * 1.5), locked=True))
    total = sum(s.words for s in out) or 1
    return [s.model_copy(update={"words": round(s.words * target / total), "min_words": round(s.min_words * target / total), "max_words": round(s.max_words * target / total)}) for s in out]


def criterion_sections(name: str, sections: list[PlanSection]) -> list[str]:
    text = name.lower()
    out = []
    for s in sections:
        words = CRITERION_WORDS.get(s.key, ())
        if any(w in text for w in words) or any(w in text for w in s.heading.lower().split() if len(w) > 5):
            out.append(s.key)
    return out


def rebalance(sections: list[PlanSection], spec: ResolvedSpec) -> list[PlanSection]:
    """Heavier scoring criteria get more depth in the sections that answer them, within each
    section's range and the total; every required section keeps its minimum (§16)."""
    weighted = [c for c in spec.scoring if c.weight]
    if not weighted or not sections:
        return sections
    total_weight = sum(c.weight or 0 for c in weighted) or 1
    even = 1 / len(weighted)
    factor = {s.key: 1.0 for s in sections}
    mapped: dict[str, list[str]] = {}
    for c in weighted:
        keys = criterion_sections(c.name, sections)
        if not keys and spec.kind == "COURSEWORK":  # "Critical analysis", "Use of evidence": the body answers them
            keys = [s.key for s in sections if s.key.startswith("theme") or s.key in ("analysis", "findings", "discussion", "reflection", "diagnosis", "evaluation")]
        mapped[c.id] = keys
        boost = 1 + max(-0.15, min(0.3, ((c.weight or 0) / total_weight - even) * 1.5))
        for key in keys:
            factor[key] = max(factor[key], boost) if boost >= 1 else min(factor[key], boost)
    target = sum(s.words for s in sections)
    raw = {s.key: s.words * factor[s.key] for s in sections}
    scale = target / (sum(raw.values()) or 1)
    out = []
    for s in sections:
        words = round(raw[s.key] * scale)
        if s.max_words:
            words = min(words, s.max_words)
        words = max(words, s.min_words)
        criteria = [c.id for c in weighted if s.key in mapped.get(c.id, [])]
        out.append(s.model_copy(update={"words": words, "criteria": criteria}))
    return out


def within(words: int, limit: float) -> bool:
    return words <= math.floor(limit)

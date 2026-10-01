"""Central resolution of what a work must satisfy (rulebook §3, §7, §9): the one place that decides,
for every requirement key, which candidate wins. Nothing else in PaperAid re-derives it.

Authority, highest first: the student's documents (call, template, addendum, brief, rubric), the
student's own choices, the document variant, PaperAid's baseline, quality guidance, and model
preference. Between two external documents an addendum (or anything marked as amending) wins,
then the more specific document (a brief over a programme handbook); two equally authoritative
documents that disagree are a conflict the student settles before that key locks.

Every decision is recorded: the winning value, what it overrode, the assumptions made when a
question was skipped, and the questions still open. The result is a versioned `ResolvedSpec`."""

import math
from typing import Any

from app.rules import library
from app.rules.extract import first_number
from app.works import directives
from app.works.models import (
    AI_NOTE,
    CoverageItem,
    Criterion,
    FormField,
    Limit,
    Question,
    Requirement,
    RequirementConflict,
    ResolvedSpec,
    SourceFile,
    WorkInputs,
)

SKIPPED = "SKIPPED"
NO_LIMIT = "NO_LIMIT"  # the student says their brief gives no word limit (never an invented one)
YES = "yes"
# The keys a work has at most one value for; every other key may have many (sections, criteria ...).
SINGLE = ("limit.words", "limit.words_min", "limit.pages", "limit.characters", "tolerance", "ceiling", "minimum_request", "currency", "duration_months",
          "deadline", "cost_share", "indirect_rate", "citation_style", "ai_policy", "source_policy", "level", "coursework_type")
# Words per page when a page limit has to be planned in words before the document is rendered.
WORDS_PER_PAGE = {"single": 500, "one_and_half": 375, "double": 275}
PLAN_SHARE_OF_LIMIT = 0.97  # a hard maximum is planned just under, so small differences never break it
STYLES = {"APA7": "APA7", "APA 7": "APA7", "APA6": "APA6", "APA 6": "APA6", "HARVARD": "HARVARD"}
AI_ANSWERS = {"BANNED": "BANNED", "ALLOWED_WITH_DISCLOSURE": "ALLOWED_WITH_DISCLOSURE", "ALLOWED": "ALLOWED", "NOT_MENTIONED": "UNKNOWN"}


def _precedence(req: Requirement, roles: dict[str, str]) -> int:
    order = library.shared()["source_precedence"]
    base = order.get(roles.get(req.source_id, "OTHER"), 1)
    return base + (2 if req.amends else 0)


def _same(a: Requirement, b: Requirement) -> bool:
    if a.number is not None and b.number is not None:
        return math.isclose(a.number, b.number)
    return " ".join(a.value.casefold().split()) == " ".join(b.value.casefold().split())


def _answer(inputs: WorkInputs, key: str) -> str:
    value = inputs.answers.get(key, "").strip()
    return "" if value in (SKIPPED, NO_LIMIT) else value


def _number(text: str) -> float | None:
    """A number the student gave ("3,000 words" as well as "3000"); answers are stored normalised."""
    return first_number(text) if text.strip() else None


def _yes(inputs: WorkInputs, key: str) -> bool:
    return inputs.answers.get(key, "").strip().lower() in ("yes", "true", "1")


def _ai_policy(raw: str) -> str:
    """The AI rule from the brief's words or the student's answer (a ban is checked before "allowed")."""
    text = raw.upper().replace(" ", "_")
    if text in AI_ANSWERS:
        return AI_ANSWERS[text]
    if any(w in text for w in ("BAN", "NOT_ALLOWED", "PROHIBIT", "MUST_NOT", "NOT_PERMITTED", "NOT_BE_USED")):
        return "BANNED"
    if any(w in text for w in ("DISCLOS", "ACKNOWLEDG", "DECLAR")):
        return "ALLOWED_WITH_DISCLOSURE"
    if "ALLOW" in text or "PERMIT" in text:
        return "ALLOWED"
    return "UNKNOWN"


def resolve(
    version: int,
    kind: str,
    variant: str,
    mode: str,
    inputs: WorkInputs,
    sources: list[SourceFile],
    external: list[Requirement],
    unclear: list[str] | None = None,
) -> ResolvedSpec:
    roles = {s.id: s.role for s in sources}
    book = library.book(kind)
    overridden: list[str] = []
    assumptions: list[str] = []
    questions: list[Question] = []
    blockers: list[str] = []
    conflicts: list[RequirementConflict] = []

    # 1. What may be used: a verified quote, or one the student confirmed. The rest is asked about.
    usable: list[Requirement] = []
    confirmed_all = _yes(inputs, "confirm:all")
    for req in external:
        req = req.model_copy(update={"confirmed": confirmed_all or _yes(inputs, f"confirm:{req.id}"), "in_conflict": False})
        declined = inputs.answers.get(f"confirm:{req.id}", "").strip().lower() == "no"
        if declined:
            overridden.append(f"{req.label}: not used, you said PaperAid misread it")
            continue
        if not req.verified and not req.confirmed:
            skipped = inputs.answers.get(f"confirm:{req.id}") == SKIPPED
            if skipped and not req.high_stakes:
                assumptions.append(f"Not used: \"{req.value}\" ({req.label}), which PaperAid could not find word for word in {req.source}.")
                continue
            questions.append(
                Question(
                    id=f"confirm:{req.id}", kind="CHOICE", choices=["yes", "no"], gate="BLOCK" if req.high_stakes else "ASK_ONCE",
                    label=f"{req.label}: \"{req.value}\" — is this what {req.source} says?",
                    help=f"PaperAid read this near \"{req.location or 'your document'}\" but could not find those exact words, so it will not use it unless you confirm.",
                    fallback="Not used.",
                )
            )
            continue
        usable.append(req)

    # 2. Single-valued keys: the highest authority wins; equal external authorities that disagree conflict.
    winners: dict[str, Requirement] = {}
    for key in SINGLE:
        candidates = sorted((r for r in usable if r.key == key and r.hard), key=lambda r: -_precedence(r, roles))
        if not candidates:
            continue
        top = candidates[0]
        rivals = [r for r in candidates[1:] if _precedence(r, roles) == _precedence(top, roles) and not _same(r, top)]
        if rivals:
            chosen = inputs.answers.get(f"conflict:{key}", "")
            pick = next((r for r in [top, *rivals] if r.id == chosen), None)
            ids = [top.id, *[r.id for r in rivals]]
            conflicts.append(RequirementConflict(key=key, requirement_ids=ids, note=f"Your documents disagree on the {top.label.lower()}.", chosen=pick.id if pick else None))
            if pick is None:
                for r in usable:
                    if r.id in ids:
                        r.in_conflict = True
                values = " or ".join(f"\"{r.value}\" ({r.source})" for r in [top, *rivals])
                questions.append(Question(id=f"conflict:{key}", kind="CHOICE", choices=ids, gate="BLOCK", label=f"Which {top.label.lower()} applies: {values}?"))
                blockers.append(f"Your documents disagree on the {top.label.lower()}: choose which applies.")
                continue
            top = pick
        for other in candidates[1:]:
            if not _same(other, top):
                overridden.append(f"{top.label}: {top.value} ({top.source}) over {other.value} ({other.source})")
        winners[key] = top

    def many(key: str) -> list[Requirement]:
        return [r for r in usable if r.key == key]

    # 3. Questions from the rulebook for this variant.
    for spec_q in book.get("questions", []):
        if spec_q.get("variants") and variant not in spec_q["variants"]:
            continue
        qid = spec_q["id"]
        value = inputs.answers.get(qid, "").strip()
        answered = bool(value)
        if qid == "problem" and not answered and len(inputs.description.split()) >= 12:
            answered = True  # the description already gives it
        if qid == "task" and not answered and len(inputs.description.split()) >= 4:
            # A short question is still the question ("Discuss the impact of social media on youth"): a
            # tester was blocked three times by a 12-word minimum the page never showed (live, 2026-10-01).
            answered = True
        if qid == "task" and not answered and (many("directive") or many("subquestion")):
            answered = True  # read from the brief
        if qid == "experience" and inputs.experience.strip():
            answered = True
        if qid == "word_limit" and "limit.words" in winners:
            answered = True  # the brief gives it
        if qid == "citation_style" and "citation_style" in winners:
            answered = True
        if qid == "ai_policy" and "ai_policy" in winners:
            answered = True
        if qid == "currency" and "currency" in winners:
            answered = True
        if qid == "duration_months" and "duration_months" in winners:
            answered = True
        if qid == "level" and "level" in winners:
            answered = True
        questions.append(Question(id=qid, label=spec_q["label"], help=spec_q.get("help", ""), kind=spec_q["kind"], choices=spec_q.get("choices", []),
                                  gate=spec_q["gate"], answered=answered, fallback=spec_q.get("fallback", "")))
        if not answered and spec_q["gate"] == "BLOCK":
            blockers.append(spec_q["label"])
        if value == SKIPPED and spec_q.get("fallback"):
            assumptions.append(f"{spec_q['label']} — skipped: {spec_q['fallback']}")

    # 4. Eligibility: the student says whether each criterion is met (FP-002, CN-042).
    eligibility = many("eligibility")
    failed = []
    for req in eligibility:
        answer = inputs.answers.get(f"eligible:{req.id}", "").strip().lower()
        questions.append(Question(id=f"eligible:{req.id}", kind="CHOICE", choices=["yes", "no"], gate="BLOCK", answered=answer in ("yes", "no"),
                                  label=f"Do you meet this eligibility criterion: \"{req.value}\"?"))
        if answer not in ("yes", "no"):
            blockers.append(f"Confirm whether you meet: {req.value}")
        elif answer == "no":
            failed.append(req.value)
    exploratory = False
    if failed:
        exploratory = _yes(inputs, "exploratory")
        questions.append(Question(id="exploratory", kind="CHOICE", choices=["yes", "no"], gate="BLOCK", answered=exploratory,
                                  label="You do not meet every eligibility criterion. Continue with an exploratory draft that is marked not submission-ready?"))
        if not exploratory:
            blockers.append("You do not meet every eligibility criterion: PaperAid can write an exploratory draft only, marked not submission-ready.")

    # 5. High-stakes items read correctly must still be confirmed once, together (§5.1).
    if any(r.high_stakes and r.verified for r in usable) and not confirmed_all:
        questions.append(Question(id="confirm:all", kind="CHOICE", choices=["yes"], gate="BLOCK", label="Confirm the limits, deadlines, money rules and AI rule PaperAid read"))
        blockers.append("Confirm what PaperAid read from your documents.")

    # 6. The values, each from the highest authority that has one.
    def value_of(key: str, answer_key: str = "") -> str:
        if key in winners:
            return winners[key].value
        return _answer(inputs, answer_key or key)

    level = (winners["level"].value.upper().replace(" ", "_") if "level" in winners else _answer(inputs, "level")) or ""
    if kind == "COURSEWORK" and level not in ("FIRST_YEAR_UG", "LATER_UG", "POSTGRADUATE"):
        level = "LATER_UG"  # the level question's own fallback (its assumption is recorded when skipped)
    style_raw = value_of("citation_style").upper()
    citation = next((v for k, v in STYLES.items() if k in style_raw), "")
    if not citation:
        citation = "APA7"
        if style_raw:
            blockers.append(f"PaperAid cannot yet produce the referencing style \"{style_raw}\"; it supports APA 7, APA 6 and Harvard.")
    ai_policy = _ai_policy(value_of("ai_policy"))
    source_raw = value_of("source_policy").upper()
    source_policy = "CLOSED" if "CLOSED" in source_raw or "ONLY" in source_raw or "SET READING" in source_raw else "INDEPENDENT"
    if variant == "REFLECTIVE" and not many("required_reading") and not source_raw:
        source_policy = "INDEPENDENT"

    limits: list[Limit] = []
    fields: list[FormField] = []
    tolerance = winners["tolerance"].number if "tolerance" in winners and winners["tolerance"].number else 0.0
    words_limit = winners.get("limit.words")
    if words_limit and words_limit.number:
        limits.append(Limit(type="WORD", max=words_limit.number, scope=words_limit.counts_toward or ["core"], tolerance=tolerance or 0.0, requirement=words_limit.id))
    elif kind == "COURSEWORK" and _number(_answer(inputs, "word_limit")):
        limits.append(Limit(type="WORD", max=float(_number(_answer(inputs, "word_limit")) or 0), scope=["core"], requirement="answer:word_limit"))
    minimum = winners.get("limit.words_min")
    if minimum and minimum.number:
        if limits and limits[0].type == "WORD":
            limits[0].min = minimum.number
        else:
            limits.append(Limit(type="WORD", max=minimum.number * 10, min=minimum.number, scope=["core"], requirement=minimum.id, blocking=False))
    pages = winners.get("limit.pages")
    if pages and pages.number:
        limits.append(Limit(type="PAGE", max=pages.number, scope=pages.counts_toward or ["core"], requirement=pages.id))
    chars = winners.get("limit.characters")
    if chars and chars.number:
        limits.append(Limit(type="CHARACTER", max=chars.number, scope=chars.counts_toward or ["core"], includes_spaces="without" not in chars.unit.lower(), requirement=chars.id))
    for n, req in enumerate(many("field"), start=1):
        if not req.number:
            continue
        in_words = "word" in req.unit.lower()
        field_id = f"field{n}"
        fields.append(FormField(id=field_id, label=req.value[:200] or f"Box {n}", max_words=int(req.number) if in_words else None,
                                max_characters=None if in_words else int(req.number), includes_spaces="without" not in req.unit.lower()))
        limits.append(Limit(type="FIELD", max=req.number, scope=[field_id], field=field_id, includes_spaces="without" not in req.unit.lower(), requirement=req.id))

    # 7. The length to plan for (§6: plan in words, check pages after rendering).
    modes = book["variants"][variant].get("modes", {})
    target = 0
    if words_limit and words_limit.number:
        target = int(words_limit.number * PLAN_SHARE_OF_LIMIT)
        if kind != "COURSEWORK" and mode in modes:
            overridden.append(f"Length: the {int(words_limit.number):,}-word limit over PaperAid's {mode.lower()} length")
    elif fields:
        target = sum(int(f.max_words or (f.max_characters or 0) / 6.5) for f in fields)
    elif kind == "COURSEWORK":
        answered = _number(_answer(inputs, "word_limit"))
        if answered:
            target = int(answered * PLAN_SHARE_OF_LIMIT)
        else:
            by_level = book.get("variant_words", {}).get(variant) or book["fallback_words"]
            target = int(by_level.get(level, 2000))
            said = "Your brief gives no word limit" if inputs.answers.get("word_limit") == NO_LIMIT else "No word limit given"
            assumptions.append(f"{said}: planned at {target:,} words, the usual length for this level.")
    else:
        target = int(modes.get(mode) or modes.get("STANDARD") or 1800)
    if pages and pages.number and not (words_limit and words_limit.number):
        spacing = "single" if kind == "FUNDING_PROPOSAL" or kind == "CONCEPT_NOTE" else "double"
        planned = int(pages.number * WORDS_PER_PAGE[spacing] * PLAN_SHARE_OF_LIMIT)
        if planned < target or not target:
            target = planned
        assumptions.append(f"Planned at about {target:,} words to fit {int(pages.number)} pages; the page count is checked on the formatted document.")

    # 8. Coursework: what the question asks.
    question_text = " ".join([inputs.description, *[r.value for r in many("directive")], *[r.quote for r in many("directive")]])
    ids = list(dict.fromkeys([*directives.find(" ".join(r.value for r in many("directive"))), *directives.find(inputs.description)])) if kind == "COURSEWORK" else []
    coverage: list[CoverageItem] = []
    if kind == "COURSEWORK":
        for n, req in enumerate(many("subquestion"), start=1):
            coverage.append(CoverageItem(id=f"Q{n}", text=req.value, directive=(directives.find(req.value) or [""])[0], requirement=req.id))
        if not coverage:
            for n, (directive, clause) in enumerate(directives.clauses(inputs.description or question_text), start=1):
                coverage.append(CoverageItem(id=f"Q{n}", text=clause[:500], directive=directive))
        if not ids and inputs.description:
            assumptions.append("No command word found in the question: it is answered as a discussion.")
            ids = ["discuss"]
    scoring = [Criterion(id=f"S{n}", name=r.value[:200], weight=r.weight or r.number, descriptor=r.quote[:600], requirement=r.id) for n, r in enumerate(many("scoring"), start=1)]
    scoring += [Criterion(id=f"K{n}", name=r.value[:200], weight=r.weight or r.number, descriptor=r.quote[:600], mandatory="must" in r.quote.lower() or "pass" in r.quote.lower(), requirement=r.id)
                for n, r in enumerate(many("rubric"), start=1)]

    # 9. Facts the rules' conditions read.
    partners = _answer(inputs, "partners")
    has_partners = bool(partners) and partners.strip().lower() not in ("no", "none", "no partners", "n/a")
    headings = [r.value for r in many("template.heading")]
    overlays = sorted({r.value.upper().split()[0] for r in many("overlay") if r.value.strip()})
    vulnerable = _yes(inputs, "vulnerable") or "SAFEGUARDING" in overlays
    personal = _yes(inputs, "personal_data") or "DATA" in overlays
    if vulnerable and "SAFEGUARDING" not in overlays:
        overlays.append("SAFEGUARDING")
    if personal and "DATA_PROTECTION" not in overlays:
        overlays.append("DATA_PROTECTION")
    required_sections = [r.value for r in many("section.required")]
    text_of_sections = " ".join(required_sections + headings).lower()
    flags = {
        "has_call": any(s.role in ("CALL", "TEMPLATE", "ADDENDUM") for s in sources),
        "has_template": bool(headings),
        "has_rubric": bool(many("rubric")),
        "has_scoring": bool(scoring),
        "form_mode": bool(fields),
        "has_partners": has_partners,
        "vulnerable": vulnerable,
        "personal_data": personal,
        "has_ceiling": "ceiling" in winners,
        "has_eligibility": bool(eligibility),
        "cost_share_required": "cost_share" in winners,
        "indirect_rule": "indirect_rate" in winners,
        "prohibited_listed": bool(many("prohibited_cost")),
        "has_overlays": bool([o for o in overlays if o not in ("SAFEGUARDING", "DATA_PROTECTION")]),
        "output_indicators_required": bool(many("output_indicators")),
        "disaggregation_required": bool(many("disaggregation")),
        "evaluation_required": bool(many("evaluation")),
        "toc_required": bool(many("theory_of_change")),
        "has_page_limit": bool(pages and pages.number),
        "budget_required": "budget" in text_of_sections or bool(_number(_answer(inputs, "budget_envelope"))),
        "timeline_required": "timeline" in text_of_sections or "workplan" in text_of_sections or bool(_number(_answer(inputs, "duration_months"))),
        "has_budget": kind == "FUNDING_PROPOSAL",
        "learning_outcomes": bool(many("learning_outcome")),
        "has_required_readings": bool(many("required_reading")),
        "empirical": _yes(inputs, "empirical") or variant == "RESEARCH_PAPER_EMPIRICAL",
        "scale_objective": "scale" in (inputs.description + " " + _answer(inputs, "intervention")).lower(),
        "executive_summary": "executive summary" in text_of_sections or target >= 3000,
        "recommendations": "recommend" in " ".join(ids) or "recommend" in text_of_sections or variant == "ACADEMIC_REPORT",
        "theory": True,
        "action_plan": True,
    }
    facts: dict[str, Any] = {**flags, "variant": variant, "mode": mode, "level": level, "ai_policy": ai_policy, "source_policy": source_policy, "directive_groups": directives.groups(ids)}
    active = [r["id"] for r in library.rules_for(kind) if library.applies(r, facts)]

    duration = int(winners["duration_months"].number) if "duration_months" in winners and winners["duration_months"].number else int(_number(_answer(inputs, "duration_months")) or 0) or None
    ceiling = winners["ceiling"].number if "ceiling" in winners else None
    if not duration and inputs.answers.get("duration_months") == SKIPPED and variant in ("FUNDING_CONCEPT", "NGO_PROJECT", "RESEARCH_GRANT"):
        duration = 12  # the question's stated fallback, recorded as an assumption above
    if ai_policy == "BANNED":
        assumptions.append(f"Your assignment does not allow AI tools, so the last page of your Word document says: \"{AI_NOTE}\"")
    for note in unclear or []:
        assumptions.append(f"Unclear in your documents: {note}")

    gate = "BLOCK" if blockers else ("ASK_ONCE" if any(not q.answered and q.gate == "ASK_ONCE" and inputs.answers.get(q.id) != SKIPPED for q in questions) else "PASS")
    return ResolvedSpec(
        version=version, kind=kind, variant=variant, mode=mode if kind != "COURSEWORK" else "", level=level if kind == "COURSEWORK" else "",  # type: ignore[arg-type]
        rules_version=library.VERSION, target_words=max(150, target), limits=limits, fields=fields, template_headings=headings,
        citation_style=citation, ai_policy=ai_policy, source_policy=source_policy,  # type: ignore[arg-type]
        required_readings=[r.value for r in many("required_reading")], scoring=scoring, directives=ids, directive_groups=directives.groups(ids),
        subject=value_of("subject") if "subject" in winners else next((r.value for r in many("subject")), ""), limiting=[r.value for r in many("limiting")],
        coverage=coverage, priorities=[r.value for r in many("priority")], eligibility=[r.value for r in eligibility], ceiling=ceiling,
        minimum_request=winners["minimum_request"].number if "minimum_request" in winners else None,
        currency=(winners["currency"].value if "currency" in winners else _answer(inputs, "currency")).upper()[:8],
        duration_months=duration, deadline=winners["deadline"].value if "deadline" in winners else "",
        cost_share=winners["cost_share"].number if "cost_share" in winners else None, cost_share_base=winners["cost_share"].unit if "cost_share" in winners else "",
        indirect_rate=winners["indirect_rate"].number if "indirect_rate" in winners else None, indirect_base=winners["indirect_rate"].unit if "indirect_rate" in winners else "",
        prohibited_costs=[r.value for r in many("prohibited_cost")], overlays=overlays, annexes=[r.value for r in many("annex")], flags=flags,
        requirements=[*usable, *[r for r in external if r.id not in {u.id for u in usable}]], conflicts=conflicts, assumptions=list(dict.fromkeys(assumptions)),
        questions=questions, gate=gate, blockers=list(dict.fromkeys(blockers)), active_rules=active, overridden=overridden, exploratory=exploratory,
    )


def facts(spec: ResolvedSpec) -> dict[str, Any]:
    """What the rules' `applies_if` conditions read, from a resolved specification."""
    return {**spec.flags, "variant": spec.variant, "mode": spec.mode, "level": spec.level, "ai_policy": spec.ai_policy, "source_policy": spec.source_policy,
            "directive_groups": spec.directive_groups}

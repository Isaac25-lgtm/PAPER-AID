"""The code validators, referenced from the rule files by id (rulebook §14). Each returns
(status, note, where) for one rule, or None when the rule has nothing to show the student (checks
that hold by construction, such as "references are rendered by code"). Semantic rules are judged by
the evaluator; their verdicts arrive through `Context.semantic`.

Statuses: PASS, FAIL, NEEDS_REVIEW (a check PaperAid cannot settle alone), NOT_APPLICABLE."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.proposals import evidence as ev
from app.proposals.models import EvidenceItem
from app.works import budget as budget_engine
from app.works import numbers
from app.works import results as results_engine
from app.works.models import AI_NOTE, Budget, Limit, ResolvedSpec, ResultsModel, WorkDocument, WorkInputs, WorkPlan

Result = tuple[str, str, str] | None
# The parts a limit's scope can name (rulebook §6.2), as the reader reports them.
REFERENCE_SCOPES = {"references", "reference_list", "bibliography", "works_cited"}
TABLE_SCOPES = {"logframe": {"logframe", "results_framework", "results_table"}, "workplan": {"workplan", "work_plan", "timeline", "gantt"},
                "mel": {"mel", "m&e", "monitoring", "indicators", "mel_table"}, "budget": {"budget", "budget_table", "detailed_budget"}}
ALL_PARTS = {"all", "everything", "whole_document", "entire_document"}
CURRENT_YEARS = 10  # evidence older than this is flagged (it may be foundational; the student decides)
OVERLAY_WORDS = {
    "SAFEGUARDING": ("safeguard", "child protection", "protection from sexual", "psea", "do no harm"),
    "DATA_PROTECTION": ("data protection", "confidential", "informed consent", "anonymi", "personal data", "data security"),
    "GENDER": ("gender", "women", "girls"),
    "DISABILITY": ("disabilit", "inclusion"),
    "ENVIRONMENT": ("environment", "environmental"),
    "CLIMATE": ("climate",),
    "LOCALISATION": ("localis", "localiz", "local partner"),
    "CONFLICT": ("conflict sensitiv", "do no harm"),
    "HUMAN": ("human rights",),
    "VALUE": ("value for money",),
}


@dataclass
class Context:
    spec: ResolvedSpec
    stage: str  # PLAN (before drafting) or FINAL (a written document)
    inputs: WorkInputs
    plan: WorkPlan | None = None
    results: ResultsModel | None = None
    budget: Budget | None = None
    doc: WorkDocument | None = None
    library: dict[str, EvidenceItem] = field(default_factory=dict)
    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)
    pages: float | None = None  # the rendered page count, when the document was rendered
    research_done: bool = True
    stripped: list[str] = field(default_factory=list)  # sections where untraceable sentences were removed
    retracted: set[str] = field(default_factory=set)
    semantic: dict[str, tuple[str, str, str]] = field(default_factory=dict)  # rule id → the evaluator's verdict
    coverage: dict[str, bool] = field(default_factory=dict)  # coursework: coverage item → answered (final review)
    priorities: dict[str, bool] = field(default_factory=dict)  # a call's priority → addressed (final review)
    measured: dict[str, tuple[str, str]] = field(default_factory=dict)  # budget and Results Model rule → (status, note)

    def __post_init__(self) -> None:
        if self.spec.kind == "FUNDING_PROPOSAL":
            if self.results is not None or self.stage == "FINAL":
                self.measured.update({rid: (status, note) for rid, status, note in results_engine.checks(self.results, self.spec)})
            if self.budget is not None:
                self.measured.update({rid: (status, note) for rid, status, note in budget_engine.checks(self.budget, self.spec, self.results)})
        elif self.budget is not None and self.budget.lines:
            self.measured.update({rid: (status, note) for rid, status, note in budget_engine.checks(self.budget, self.spec, self.results) if rid == "CN-022"})
        elif self.spec.ceiling is not None and self.spec.kind == "CONCEPT_NOTE":
            envelope = self.inputs.answers.get("budget_envelope", "").replace(",", "").strip()
            if envelope.replace(".", "", 1).isdigit():
                amount = float(envelope)
                self.measured["CN-022"] = ("FAIL" if amount > self.spec.ceiling else "PASS",
                                           f"Your indicative budget of {budget_engine.money(amount, self.spec.currency)} against a ceiling of {budget_engine.money(self.spec.ceiling, self.spec.currency)}.")

    # --- the written text ---------------------------------------------------------------------
    def sections(self) -> list[tuple[str, str, str]]:
        """(key, heading, rendered text) of each written section: number tokens filled, citations
        rendered in the required style, so lengths are measured as the student will see them."""
        if self.doc is None:
            return []
        citer = ev.Citer(self.library, self.spec.citation_style)  # as the Word file renders them
        out = []
        for s in self.doc.sections:
            text = " ".join(numbers.render(citer.render(p), self.tokens)[0] for p in s.paragraphs)
            out.append((s.key, s.heading, text))
        return out

    def words(self, keys: set[str] | None = None) -> int:
        return sum(len(t.split()) for k, _, t in self.sections() if keys is None or k in keys)

    # --- what a limit counts (rulebook §6.2; Codex audit 2026-09-30 #5) --------------------------
    def limit_texts(self, limit: Limit) -> tuple[list[str], list[str]]:
        """The rendered texts a limit counts, and those it may count because the instructions do not
        say. Each section's text and its own table always count (they are the narrative). The
        reference list and the tables code renders count when the limit's scope names them; when no
        scope is stated they "may count", and a total over the limit with them is flagged."""
        if self.doc is None:
            return [], []
        from app.works.export import generated_tables

        scope = {s.lower().replace(" ", "_") for s in limit.scope}
        keys = {s.key for s in self.doc.sections}
        only = scope if scope and scope <= keys else None  # a limit on named sections only
        citer = ev.Citer(self.library, self.spec.citation_style)
        counted: list[str] = []
        for s in self.doc.sections:
            if only is not None and s.key not in only:
                continue
            counted += [numbers.render(citer.render(p), self.tokens)[0] for p in s.paragraphs]
            if s.table:
                counted += [numbers.render(citer.render(c), self.tokens)[0] for c in [s.table_caption, *[c for row in s.table for c in row]]]
        if only is not None:
            return counted, []
        stated = scope - {"core"}
        possible: list[str] = []
        whole = bool(stated & ALL_PARTS)
        refs = ev.reference_list([self.library[i].source for i in self.cited() if i in self.library], self.spec.citation_style)
        if whole or stated & REFERENCE_SCOPES:
            counted += refs
        elif not stated:
            possible += refs
        for _, kind, rows, caption in generated_tables(self.doc, self.spec, self.results, self.budget):
            text = [caption, *[c for row in rows for c in row]]
            if whole or stated & TABLE_SCOPES[kind] or "tables" in stated or "embedded_tables" in stated:
                counted += text
            elif not stated:
                possible += text
        return counted, possible

    def cited(self) -> list[str]:
        return list(self.doc.cited) if self.doc else []


def _ok(note: str) -> Result:
    return ("PASS", note, "")


def _measured(ctx: Context, rule: dict[str, Any]) -> Result:
    found = ctx.measured.get(rule["id"])
    if found is None:
        return None if ctx.stage == "PLAN" else ("NOT_APPLICABLE", "Not measured.", "")
    return (found[0], found[1], "")


def _hidden(ctx: Context, rule: dict[str, Any]) -> Result:
    return None


def _limits_hard_max(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    problems, notes = [], []
    for limit in ctx.spec.limits:
        if limit.type == "WORD":
            counted, possible = ctx.limit_texts(limit)
            words, extra = _count_words(counted), _count_words(possible)
            allowed = limit.max * (1 + limit.tolerance / 100)
            notes.append(f"{words:,} words against a limit of {int(limit.max):,}")
            if words > allowed:
                problems.append(f"{words:,} words is over the {int(limit.max):,}-word limit")
            elif words + extra > allowed:  # usually they do not count; the student is told the total if they do
                notes.append(f"{words + extra:,} with the references and tables, if your instructions count them (they do not say)")
        elif limit.type == "CHARACTER":
            counted, possible = ctx.limit_texts(limit)
            chars, extra = _count_chars(counted, limit.includes_spaces), _count_chars(possible, limit.includes_spaces)
            notes.append(f"{chars:,} characters against {int(limit.max):,}")
            if chars > limit.max:
                problems.append(f"{chars:,} characters is over the {int(limit.max):,}-character limit")
            elif chars + extra > limit.max:
                notes.append(f"{chars + extra:,} with the references and tables, if your instructions count them (they do not say)")
        elif limit.type == "PAGE":
            if ctx.pages is None:
                counted, possible = ctx.limit_texts(limit)
                estimate = _count_words(counted + possible) / 500
                return ("NEEDS_REVIEW", f"About {estimate:.1f} pages at single spacing, estimated from its words. Check the page count in Word against the {int(limit.max)}-page limit.", "")
            notes.append(f"{ctx.pages:g} pages (counted by PaperAid's renderer) against {int(limit.max)}")
            if ctx.pages > limit.max:
                problems.append(f"{ctx.pages:g} pages is over the {int(limit.max)}-page limit")
    if not notes and not problems:
        return None
    if problems:
        return ("FAIL", "; ".join(problems), "")
    return _ok("; ".join(notes) + ".")


def _count_words(texts: list[str]) -> int:
    return sum(len(t.split()) for t in texts)


def _count_chars(texts: list[str], spaces: bool) -> int:
    return sum(len(t if spaces else t.replace(" ", "")) for t in texts)


def _rendered_pages(ctx: Context, rule: dict[str, Any]) -> Result:
    page = next((limit for limit in ctx.spec.limits if limit.type == "PAGE"), None)
    if page is None or ctx.doc is None:
        return None
    if ctx.pages is None:
        return ("NEEDS_REVIEW", "The page count is estimated, not measured on the formatted document: check it in Word.", "")
    # PaperAid's renderer and Word can differ slightly, so a count must leave a 5% margin to pass.
    if ctx.pages <= page.max * 0.95:
        return _ok(f"{ctx.pages:g} pages in PaperAid's rendering of the Word file; the limit is {int(page.max)}. Confirm in Word.")
    return ("FAIL" if ctx.pages > page.max else "NEEDS_REVIEW", f"{ctx.pages:g} pages against a limit of {int(page.max)}: check the page count in Word.", "")


def _word_tolerance(ctx: Context, rule: dict[str, Any]) -> Result:
    limit = next((lim for lim in ctx.spec.limits if lim.type == "WORD"), None)
    if ctx.doc is None:
        return None
    if limit is None:
        return _ok(f"{ctx.words():,} words against PaperAid's planned {ctx.spec.target_words:,} (no limit was given).")
    words = _count_words(ctx.limit_texts(limit)[0])
    allowed = limit.max * (1 + limit.tolerance / 100)
    if words > allowed:
        return ("FAIL", f"{words:,} words is over the {int(limit.max):,}-word limit{' and its stated tolerance' if limit.tolerance else ''}.", "")
    if words < limit.max * 0.85:
        return ("NEEDS_REVIEW", f"{words:,} words is well under the {int(limit.max):,}-word limit.", "")
    return _ok(f"{words:,} words against a limit of {int(limit.max):,}{f' (tolerance {limit.tolerance:g}% as stated)' if limit.tolerance else ' (no tolerance assumed)'}.")


def _field_count(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.fields or ctx.doc is None:
        return None
    by_field = {s.field_id: s for s in ctx.doc.sections if s.field_id}
    rendered = {k: t for k, _, t in ctx.sections()}
    over = []
    for f in ctx.spec.fields:
        section = by_field.get(f.id)
        if section is None:
            over.append(f"\"{f.label}\" is empty")
            continue
        text = rendered.get(section.key, "")
        if f.max_characters and len(text if f.includes_spaces else text.replace(" ", "")) > f.max_characters:
            over.append(f"\"{f.label}\" has {len(text):,} characters (limit {f.max_characters:,})")
        if f.max_words and len(text.split()) > f.max_words:
            over.append(f"\"{f.label}\" has {len(text.split()):,} words (limit {f.max_words:,})")
    return ("FAIL", "; ".join(over), "") if over else _ok("Every form box is within its limit.")


def _fields_typed(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.fields:
        return None
    return _ok(f"{len(ctx.spec.fields)} form boxes, each with its own limit.")


def _heading_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}


def _required_sections(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    written = {s.key for s in ctx.doc.sections if any(p.strip() for p in s.paragraphs)}
    headings = [s.heading for s in ctx.doc.sections]
    missing = [s.heading for s in (ctx.plan.sections if ctx.plan else []) if s.required and s.key not in written]
    for required in ctx.spec.template_headings + [r.value for r in ctx.spec.requirements if r.key == "section.required"]:
        words = _heading_words(required)
        if words and not any(words & _heading_words(h) for h in headings):
            missing.append(required)
    missing = list(dict.fromkeys(missing))
    return ("FAIL", "Missing: " + "; ".join(missing), "") if missing else _ok("Every required section is present.")


def _mandatory_kept(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.plan is None or not ctx.spec.template_headings:
        return None
    planned = {s.heading for s in ctx.plan.sections}
    missing = [h for h in ctx.spec.template_headings if h[:200] not in planned]
    return ("FAIL", "The plan dropped required headings: " + "; ".join(missing), "") if missing else _ok("Every heading your template requires is in the plan.")


def _order(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.template_headings:
        return None
    source = [s.heading for s in ctx.doc.sections] if ctx.doc else [s.heading for s in ctx.plan.sections] if ctx.plan else []
    positions = [next((i for i, h in enumerate(source) if h.strip().lower() == t.strip().lower()[:200]), -1) for t in ctx.spec.template_headings]
    found = [p for p in positions if p >= 0]
    if len(found) < len(positions):
        return ("FAIL", "Some required headings are missing.", "")
    return _ok("The headings follow the template's order.") if found == sorted(found) else ("FAIL", "The headings are not in the template's order.", "")


def _conditional_section(ctx: Context, rule: dict[str, Any]) -> Result:
    keys = set(rule.get("sections", []))
    have = {s.key for s in ctx.doc.sections} if ctx.doc else {s.key for s in ctx.plan.sections} if ctx.plan else set()
    return _ok("Included.") if keys & have else ("FAIL", f"Add the section: {rule['ui_message']}.", "")


def _scoring_mapped(ctx: Context, rule: dict[str, Any]) -> Result:
    weighted = [c for c in ctx.spec.scoring if c.weight]
    if not weighted or ctx.plan is None:
        return None
    covered = {c for s in ctx.plan.sections for c in s.criteria}
    loose = [c.name for c in weighted if c.id not in covered]
    return ("NEEDS_REVIEW", "Not tied to a section yet: " + "; ".join(loose), "") if loose else _ok("Every weighted criterion shapes at least one section.")


def _balance(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.plan is None:
        return None
    outside = [f"{s.heading} ({s.words} words; {s.min_words}-{s.max_words})" for s in ctx.plan.sections if s.max_words and not s.min_words <= s.words <= s.max_words]
    return ("NEEDS_REVIEW", "Outside PaperAid's usual range: " + "; ".join(outside), "") if outside else _ok("Every section is within its usual range.")


def _objective_count(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.results is None:
        return None
    n = len(ctx.results.objectives)
    return _ok(f"{n} objectives.") if 2 <= n <= 4 else ("NEEDS_REVIEW", f"{n} objectives; two to four is usual.", "")


def _complexity(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.spec.kind != "FUNDING_PROPOSAL" or ctx.results is None:
        return None
    score = sum([
        len(ctx.results.outcomes) > 3, len(ctx.results.activities) > 15, len(ctx.results.indicators) > 12, ctx.spec.flags.get("has_partners", False),
        (ctx.spec.duration_months or 12) > 24, len(ctx.budget.lines) > 40 if ctx.budget else False, len(ctx.spec.annexes) > 3,
    ])
    suggested = "COMPREHENSIVE" if score >= 4 else "STANDARD" if score >= 1 else "COMPACT"
    if ctx.spec.mode == suggested or any(limit.type in ("WORD", "PAGE") for limit in ctx.spec.limits):
        return None
    return ("NEEDS_REVIEW", f"The project's complexity suggests a {suggested.lower()} proposal; you chose {ctx.spec.mode.lower()}.", "")


def _refs_exist(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    bad = [i for i in ctx.cited() if i not in ctx.library or not ctx.library[i].usable]
    return ("FAIL", f"{len(bad)} citations are not confirmed.", "") if bad else _ok(f"{len({ctx.library[i].source.doi or ctx.library[i].source.url for i in ctx.cited()})} sources, each found and checked by PaperAid.")


def _claims_supported(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    usable = {i for i, item in ctx.library.items() if item.usable}
    problems = [p for s in ctx.doc.sections for par in s.paragraphs for p in ev.citation_problems(numbers.strip(par), usable)]
    if problems:
        return ("FAIL", problems[0], "")
    if ctx.stripped:
        return ("NEEDS_REVIEW", f"PaperAid withheld sentences it could not trace to confirmed evidence in: {', '.join(ctx.stripped)}. Check those sections still read well.", "")
    return _ok("Every citation points to evidence PaperAid confirmed.")


def _not_contradicted(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    bad = [i for i in ctx.cited() if i in ctx.library and ctx.library[i].support == "CONTRADICTED"]
    return ("FAIL", "A cited source contradicts its claim.", "") if bad else _ok("No cited source contradicts its claim.")


def _current(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    from app.jobs.models import utcnow

    year = utcnow().year
    old = sorted({f"{ev.author_label(ctx.library[i].source)} ({ctx.library[i].source.year})" for i in ctx.cited() if i in ctx.library
                  and ctx.library[i].source.year.isdigit() and year - int(ctx.library[i].source.year) > CURRENT_YEARS})
    return ("NEEDS_REVIEW", "Older sources (fine if foundational): " + "; ".join(old), "") if old else _ok("The evidence is recent.")


def _intext_mapping(ctx: Context, rule: dict[str, Any]) -> Result:
    return None if ctx.doc is None else _ok("The reference list is built from exactly the sources cited.")


def _style(ctx: Context, rule: dict[str, Any]) -> Result:
    names = {"APA7": "APA 7th edition", "APA6": "APA 6th edition", "HARVARD": "Harvard"}
    return None if ctx.doc is None else _ok(f"Citations and references are rendered in {names[ctx.spec.citation_style]} by PaperAid.")


def _retraction(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    bad = [i for i in ctx.cited() if i in ctx.library and ctx.library[i].source.doi in ctx.retracted]
    return ("FAIL", "A cited source has been retracted.", "") if bad else _ok("No cited source is known to be retracted.")


def _figures_supported(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    unknown = [t for s in ctx.doc.sections for p in s.paragraphs for t in numbers.render(p, ctx.tokens)[1]]
    if unknown:
        return ("FAIL", f"Figures PaperAid could not fill: {', '.join(dict.fromkeys(unknown))}.", "")
    if ctx.stripped:
        return ("NEEDS_REVIEW", "Some sentences with figures PaperAid could not trace were withheld.", "")
    return _ok("Every figure comes from its source, your answers or your budget and Results Model.")


def _consistency(ctx: Context, rule: dict[str, Any]) -> Result:
    result = _figures_supported(ctx, rule)
    measured = ctx.measured.get(rule["id"])
    if measured and measured[0] == "FAIL":
        return ("FAIL", measured[1], "")
    return result


def _conflict(ctx: Context, rule: dict[str, Any]) -> Result:
    open_ = [c for c in ctx.spec.conflicts if c.chosen is None]
    if not ctx.spec.conflicts:
        return None
    return ("FAIL", "Your documents still disagree on: " + "; ".join(c.key for c in open_), "") if open_ else _ok("You settled where your documents disagreed.")


def _provenance(ctx: Context, rule: dict[str, Any]) -> Result:
    external = [r for r in ctx.spec.requirements if r.authority == "EXTERNAL_MANDATORY"]
    if not external:
        return None
    bare = [r.label for r in external if not r.quote or not r.source]
    return ("FAIL", "Without a quote: " + "; ".join(bare), "") if bare else _ok(f"{len(external)} requirements, each with its quote and place in your documents.")


def _unverified(ctx: Context, rule: dict[str, Any]) -> Result:
    used = [r for r in ctx.spec.requirements if r.authority == "EXTERNAL_MANDATORY" and not r.verified and r.confirmed]
    return _ok(f"You confirmed {len(used)} requirement(s) PaperAid could not find word for word.") if used else None


def _extracted(ctx: Context, rule: dict[str, Any]) -> Result:
    read = any(r.authority == "EXTERNAL_MANDATORY" for r in ctx.spec.requirements)
    return _ok("The call's requirements were read and confirmed.") if read else ("FAIL", "Read your call or template before drafting.", "")


def _eligibility(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.eligibility:
        return None
    unmet = [q.label for q in ctx.spec.questions if q.id.startswith("eligible:") and ctx.inputs.answers.get(q.id, "").lower() == "no"]
    if ctx.spec.exploratory or unmet:
        return ("FAIL", "Not every eligibility criterion is met, so this is an exploratory draft, not ready to submit.", "")
    return _ok("You confirmed you meet each eligibility criterion.")


def _eligibility_evaluated(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.eligibility:
        return None
    open_ = [q for q in ctx.spec.questions if q.id.startswith("eligible:") and not q.answered]
    return ("FAIL", "Confirm each eligibility criterion.", "") if open_ else _ok("Each eligibility criterion was answered before drafting.")


def _gate(question: str) -> Callable[[Context, dict[str, Any]], Result]:
    def check(ctx: Context, rule: dict[str, Any]) -> Result:
        q = next((q for q in ctx.spec.questions if q.id == question), None)
        if q is None:
            return None
        return _ok("Given.") if q.answered else ("FAIL", q.label, "")

    return check


def _core_inputs(ctx: Context, rule: dict[str, Any]) -> Result:
    open_ = [q.label for q in ctx.spec.questions if q.id in ("problem", "intervention") and not q.answered]
    return ("FAIL", "; ".join(open_), "") if open_ else _ok("You described the problem and the intervention.")


def _priorities(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.priorities or ctx.doc is None:
        return None
    missed = [p for p in ctx.spec.priorities if not ctx.priorities.get(p, False)]
    return ("FAIL", "Not yet addressed: " + "; ".join(missed), "") if missed else _ok("Every priority area in the call is addressed.")


def _overlay(name: str) -> Callable[[Context, dict[str, Any]], Result]:
    def check(ctx: Context, rule: dict[str, Any]) -> Result:
        if ctx.doc is None:
            return None
        text = " ".join(t for _, _, t in ctx.sections()).lower()
        found = any(w in text for w in OVERLAY_WORDS[name])
        return _ok(f"{name.replace('_', ' ').title()} is addressed.") if found else ("FAIL", f"Address {name.replace('_', ' ').lower()}.", "")

    return check


def _overlays_required(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    text = " ".join(t for _, _, t in ctx.sections()).lower()
    missing = [o for o in ctx.spec.overlays if o not in ("SAFEGUARDING", "DATA_PROTECTION") and not any(w in text for w in OVERLAY_WORDS.get(o, (o.lower(),)))]
    return ("FAIL", "Not addressed: " + ", ".join(m.lower() for m in missing), "") if missing else _ok("Every cross-cutting theme the call asks for is addressed.")


def _logframe(ctx: Context, rule: dict[str, Any]) -> Result:
    return _measured(ctx, {"id": "FP-073"}) if ctx.doc else None


def _coverage(ctx: Context, rule: dict[str, Any]) -> Result:
    items = ctx.spec.coverage
    if not items:
        return None
    if ctx.stage == "PLAN":
        if ctx.plan is None:
            return None
        planned = {c for s in ctx.plan.sections for c in s.coverage}
        loose = [i.text[:80] for i in items if i.id not in planned]
        return ("FAIL", "Not planned yet: " + "; ".join(loose), "") if loose else _ok("Every part of the question has a section.")
    missed = [i.text[:80] for i in items if not ctx.coverage.get(i.id, False)]
    return ("FAIL", "Not answered: " + "; ".join(missed), "") if missed else _ok(f"All {len(items)} parts of the question are answered.")


def _parsed(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.directives:
        return ("NEEDS_REVIEW", "No command word was found in the question.", "")
    return _ok("Asks you to: " + ", ".join(d.replace("_", " ") for d in ctx.spec.directives) + ".")


def _rubric_parsed(ctx: Context, rule: dict[str, Any]) -> Result:
    rubric = [c for c in ctx.spec.scoring if c.id.startswith("K")]
    return _ok(f"{len(rubric)} rubric criteria read.") if rubric else ("FAIL", "The rubric could not be read.", "")


def _intro_share(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    total = ctx.words() or 1
    intro = ctx.words({"introduction"})
    return _ok(f"The introduction is {intro / total:.0%} of the text.") if intro / total <= 0.15 else ("NEEDS_REVIEW", f"The introduction is {intro / total:.0%} of the text.", "introduction")


def _conclusion_new(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    earlier = {i for s in ctx.doc.sections if s.key != "conclusion" for p in s.paragraphs for i in ev.cited_ids(p)}
    new = {i for s in ctx.doc.sections if s.key == "conclusion" for p in s.paragraphs for i in ev.cited_ids(p)} - earlier
    return ("NEEDS_REVIEW", "The conclusion cites sources the body does not use.", "conclusion") if new else _ok("The conclusion brings no new evidence.")


def _no_artificial_methods(ctx: Context, rule: dict[str, Any]) -> Result:
    have = {s.key for s in (ctx.doc.sections if ctx.doc else ctx.plan.sections if ctx.plan else [])}
    return ("FAIL", "Remove the methods section from a non-empirical paper.", "") if "methods" in have else None


def _ai_policy(ctx: Context, rule: dict[str, Any]) -> Result:
    policy = ctx.spec.ai_policy
    if ctx.doc is None:
        return None
    if policy == "BANNED":
        return _ok("Your assignment does not allow AI tools; the note is on the last page.")
    if policy == "ALLOWED_WITH_DISCLOSURE":
        return _ok("A disclosure statement is on the last page.")
    if policy == "UNKNOWN":
        return _ok("Your assignment says nothing about AI; " + ("the note is on the last page." if ctx.doc.ai_note else "you chose to leave out the note."))
    return None


def _ai_note(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None or ctx.spec.ai_policy != "BANNED":
        return None
    return _ok(f"The last page says: \"{AI_NOTE}\"") if ctx.doc.ai_note == AI_NOTE else ("FAIL", "The last-page note is missing.", "")


def _source_restriction(ctx: Context, rule: dict[str, Any]) -> Result:
    if ctx.doc is None:
        return None
    outside = [i for i in ctx.cited() if i in ctx.library and not ctx.library[i].source.url.startswith("reading:")]
    return ("FAIL", "Sources outside your set readings are cited.", "") if outside else _ok("Only your set readings are cited.")


def _research_done(ctx: Context, rule: dict[str, Any]) -> Result:
    return _ok("PaperAid researched and confirmed its sources.") if ctx.research_done else ("NEEDS_REVIEW", "Little confirmed evidence was found; add sources you have.", "")


def _required_readings(ctx: Context, rule: dict[str, Any]) -> Result:
    if not ctx.spec.required_readings or ctx.doc is None:
        return None
    titles = [_heading_words(ctx.library[i].source.title + " " + " ".join(ctx.library[i].source.authors)) for i in ctx.cited() if i in ctx.library]
    missing = [r for r in ctx.spec.required_readings if not any(len(_heading_words(r) & t) >= 2 for t in titles)]
    return ("NEEDS_REVIEW", "Not cited yet: " + "; ".join(missing), "") if missing else _ok("Every required reading is used.")


def _tables(rule_id: str) -> Callable[[Context, dict[str, Any]], Result]:
    def check(ctx: Context, rule: dict[str, Any]) -> Result:
        return _measured(ctx, {"id": rule_id}) if ctx.doc or ctx.stage == "PLAN" else None

    return check


VALIDATORS: dict[str, Callable[[Context, dict[str, Any]], Result]] = {
    "requirements.precedence": _hidden, "requirements.persisted": _hidden, "requirements.governing_source": _hidden, "limits.typed": _hidden,
    "plan.word_default": _hidden, "plan.user_preferences": _hidden, "readiness.blocking": _hidden, "readiness.report": _hidden,
    "readiness.internal_labels": _hidden, "pipeline.no_evasion": _hidden, "references.metadata": _hidden, "work.variant": _hidden,
    "limits.external_override": _hidden, "coursework.source_count_label": _hidden,
    "requirements.provenance": _provenance, "requirements.unverified_not_locked": _unverified, "requirements.conflict": _conflict,
    "requirements.extracted": _extracted,
    "limits.rendered_pages": _rendered_pages, "limits.hard_max": _limits_hard_max, "limits.field_count": _field_count, "limits.fields_typed": _fields_typed,
    "structure.mandatory_kept": _mandatory_kept, "structure.required_sections": _required_sections, "structure.template_match": _mandatory_kept,
    "structure.order": _order, "structure.conditional_section": _conditional_section,
    "plan.scoring_mapped": _scoring_mapped, "plan.balance": _balance, "plan.objective_count": _objective_count, "plan.complexity": _complexity,
    "references.exists": _refs_exist, "claims.supported": _claims_supported, "claims.not_contradicted": _not_contradicted, "references.current": _current,
    "references.intext_mapping": _intext_mapping, "references.style": _style, "references.retraction": _retraction,
    "numbers.user_figures": _figures_supported, "numbers.supported": _figures_supported, "numbers.consistency": _consistency,
    "eligibility.thresholds": _eligibility, "eligibility.evaluated": _eligibility_evaluated,
    "gate.core_inputs": _core_inputs, "gate.task_present": _gate("task"), "gate.experience_present": _gate("experience"),
    "call.priorities_addressed": _priorities,
    "overlay.safeguarding": _overlay("SAFEGUARDING"), "overlay.data_protection": _overlay("DATA_PROTECTION"), "overlay.required": _overlays_required,
    "tables.logframe": _logframe, "tables.workplan": _tables("FP-074"), "tables.mel": _tables("FP-075"),
    "coursework.parsed": _parsed, "coursework.subquestion_coverage": _coverage, "coursework.word_tolerance": _word_tolerance,
    "coursework.rubric_parsed": _rubric_parsed, "coursework.intro_share": _intro_share, "coursework.conclusion_new_evidence": _conclusion_new,
    "coursework.no_artificial_methods": _no_artificial_methods, "coursework.ai_policy": _ai_policy, "coursework.ai_note": _ai_note,
    "coursework.source_restriction": _source_restriction, "coursework.research_done": _research_done, "coursework.required_readings": _required_readings,
}
for _name in ("results.exists", "results.activity_output_link", "results.output_outcome_link", "results.outcome_indicator_link", "results.output_indicator_link",
              "results.indicator_level", "results.indicator_fields", "results.disaggregation", "results.risk_owner", "timeline.activity_coverage",
              "budget.activity_mapping", "budget.line_purpose", "budget.line_math", "budget.subtotals", "budget.ceiling", "budget.cost_share",
              "budget.indirect_cost", "budget.prohibited_costs", "budget.years", "budget.currency", "budget.mel_resources", "staff.effort_consistency"):
    VALIDATORS[_name] = _measured

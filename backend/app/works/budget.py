"""The budget engine (rulebook §12.10, Appendix E). Money is structured numbers and code does every
sum: line totals, category and year subtotals, the grand total, the ceiling, cost share, indirect
costs, currency conversion and staff effort. Nothing written by a model can change a figure."""

import re
from dataclasses import dataclass

from app.works.models import Budget, BudgetLine, ResolvedSpec, ResultsModel

INDIRECT = re.compile(r"\b(indirect|overhead|admin(istrative)? overhead|nicra)\b", re.IGNORECASE)
PERSONNEL = re.compile(r"\b(personnel|staff|salar(y|ies)|wages|human resources)\b", re.IGNORECASE)
MEL_WORDS = re.compile(r"\b(monitoring|evaluation|m&e|mel|baseline|endline|survey|data collection|learning)\b", re.IGNORECASE)
ROUND = 0.005  # half a cent: sums are compared after rounding to cents


def line_total(line: BudgetLine) -> float:
    return round(line.quantity * line.unit_cost, 2)


@dataclass(frozen=True)
class Totals:
    total: float
    direct: float
    indirect: float
    personnel: float
    by_category: dict[str, float]
    by_year: dict[int, float]


def complete(budget: Budget) -> bool:
    """Every line has its quantity and unit cost (the applicant's figures)."""
    return all(li.quantity and li.unit_cost for li in budget.lines)


def totals(budget: Budget) -> Totals:
    by_category: dict[str, float] = {}
    by_year: dict[int, float] = {}
    indirect = personnel = 0.0
    for line in budget.lines:
        amount = line_total(line)
        by_category[line.category] = round(by_category.get(line.category, 0.0) + amount, 2)
        by_year[line.year] = round(by_year.get(line.year, 0.0) + amount, 2)
        if INDIRECT.search(line.category) or INDIRECT.search(line.description):
            indirect += amount
        if PERSONNEL.search(line.category):
            personnel += amount
    total = round(sum(line_total(li) for li in budget.lines), 2)
    return Totals(total=total, direct=round(total - indirect, 2), indirect=round(indirect, 2), personnel=round(personnel, 2), by_category=by_category, by_year=by_year)


Check = tuple[str, str, str]  # (rule id, PASS | FAIL | NEEDS_REVIEW | NOT_APPLICABLE, note)


def money(value: float, currency: str) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return f"{currency} {text}".strip()


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4}


def checks(budget: Budget, spec: ResolvedSpec, results: ResultsModel | None) -> list[Check]:
    """Every budget rule, measured. A rule whose condition does not hold is NOT_APPLICABLE."""
    t = totals(budget)
    cur = budget.currency
    out: list[Check] = []
    if not budget.lines:
        return [("FP-039", "FAIL", "The budget has no lines yet: add them in the budget table.")]
    wrong = [f"{li.id} ({li.description[:40]}): {money(li.entered_total, cur)} entered, {money(line_total(li), cur)} is its quantity times unit cost"
             for li in budget.lines if li.entered_total is not None and abs(li.entered_total - line_total(li)) > ROUND]
    out.append(("FP-039", "FAIL" if wrong else "PASS", "; ".join(wrong) or "Every line's total is its quantity times its unit cost (calculated by PaperAid)."))
    out.append(("FP-040", "PASS", f"Categories add up to the grand total of {money(t.total, cur)}."))
    out.append(("FP-045", "PASS" if abs(sum(t.by_year.values()) - t.total) <= ROUND else "FAIL",
                f"Year totals: {', '.join(f'year {y}: {money(v, cur)}' for y, v in sorted(t.by_year.items()))}."))
    request = budget.requested if budget.requested is not None else t.total
    if budget.requested is not None and abs(budget.requested - t.total) > ROUND:
        out.append(("FP-048", "FAIL", f"The amount requested ({money(budget.requested, cur)}) differs from the budget's total ({money(t.total, cur)})."))
    if spec.ceiling is not None:
        over = request - spec.ceiling
        out.append(("FP-041", "FAIL" if over > ROUND else "PASS", f"{money(request, cur)} requested against a ceiling of {money(spec.ceiling, spec.currency or cur)}."))
        out.append(("CN-022", "FAIL" if over > ROUND else "PASS", f"{money(request, cur)} against a ceiling of {money(spec.ceiling, spec.currency or cur)}."))
    if spec.minimum_request is not None and request + ROUND < spec.minimum_request:
        out.append(("FP-041", "FAIL", f"{money(request, cur)} is below the call's minimum of {money(spec.minimum_request, cur)}."))
    if spec.cost_share is not None:
        base = spec.cost_share_base.lower()
        provided = budget.cost_share_provided or 0.0
        if "request" in base:
            required = spec.cost_share / 100 * request
        else:  # of the total project cost (the donor's request plus the applicant's share)
            required = spec.cost_share / 100 * (request + provided)
        out.append(("FP-042", "FAIL" if provided + ROUND < required else "PASS",
                    f"{money(provided, cur)} provided; {spec.cost_share:g}% of {'the request' if 'request' in base else 'the total project cost'} is {money(required, cur)}."))
    if spec.indirect_rate is not None:
        base = spec.indirect_base.lower()
        if "personnel" in base or "salar" in base:
            base_amount, base_name = t.personnel, "personnel costs"
        elif "direct" in base or not base:
            base_amount, base_name = t.direct, "total direct costs"
        else:
            base_amount, base_name = t.direct, f"\"{spec.indirect_base}\" (read as total direct costs; check it)"
        allowed = spec.indirect_rate / 100 * base_amount
        status = "FAIL" if t.indirect > allowed + ROUND else ("NEEDS_REVIEW" if "check it" in base_name else "PASS")
        out.append(("FP-043", status, f"Indirect costs {money(t.indirect, cur)}; allowed {spec.indirect_rate:g}% of {base_name} = {money(allowed, cur)}."))
    if spec.prohibited_costs:
        hits = []
        for item in spec.prohibited_costs:
            words = _content_words(item)
            for li in budget.lines:
                if words and words <= _content_words(li.category + " " + li.description):
                    hits.append(f"{li.id} ({li.description[:40]}) looks like \"{item}\"")
        out.append(("FP-044", "FAIL" if hits else "PASS", "; ".join(hits) or "No budget line matches a cost the call prohibits."))
    if budget.exchange_from and budget.exchange_from != cur:
        out.append(("FP-046", "PASS" if budget.exchange_rate and budget.exchange_date else "FAIL",
                    "The exchange rate and its date are stated." if budget.exchange_rate and budget.exchange_date else "Give the exchange rate used and its date."))
    else:
        out.append(("FP-046", "NOT_APPLICABLE", "No currency conversion."))
    activity_ids = {a.id for a in results.activities} if results else set()
    costed = {a.id for a in results.activities if a.costed} if results else set()
    mapped = {aid for li in budget.lines for aid in li.activity_ids}
    unfunded = sorted(costed - mapped)
    out.append(("FP-037", "FAIL" if unfunded else "PASS", f"Activities with no budget line: {', '.join(unfunded)}." if unfunded else "Every costed activity has a budget line."))
    orphan = [li.id for li in budget.lines if not li.support and not (set(li.activity_ids) & activity_ids) and not INDIRECT.search(li.category + " " + li.description)]
    out.append(("FP-038", "FAIL" if orphan else "PASS", f"Lines tied to no activity or declared support cost: {', '.join(orphan)}." if orphan else "Every line belongs to an activity or a declared support cost."))
    staff = [li for li in budget.lines if li.role and "month" in li.unit.lower()]
    # A staff line's months beyond the project's length are fine only when several people share the
    # role, which the budget cannot show: the student checks it.
    too_long = [f"{li.id} ({li.role}): {li.quantity:g} months" for li in staff if spec.duration_months and li.quantity > spec.duration_months]
    roles = {a.owner_role.lower() for a in (results.activities if results else [])} | {i.responsible_role.lower() for i in (results.indicators if results else [])}
    unknown = [li.role for li in staff if li.role.lower() not in roles]
    note = "; ".join([*(f"more months than the project lasts (check how many people share the role): {x}" for x in too_long), *(f"'{r}' has no activity or indicator" for r in unknown)])
    out.append(("FP-047", "NEEDS_REVIEW" if too_long or unknown else "PASS", note or "Staff time fits the project's duration and roles."))
    has_mel = any(MEL_WORDS.search(li.category + " " + li.description) for li in budget.lines)
    out.append(("FP-054", "PASS" if has_mel else "NEEDS_REVIEW", "Monitoring and evaluation have budget lines." if has_mel else "No budget line pays for monitoring, evaluation or data collection."))
    return out

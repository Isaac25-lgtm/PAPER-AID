"""The Results Model's checks and the tables rendered from it (rulebook §12.6-12.9, Appendix F).
The logframe, workplan and M&E table are built here by code from the one model, so they can never
disagree with it or with each other (FP-073 to FP-075)."""

from app.works.budget import Check
from app.works.models import Indicator, ResolvedSpec, ResultsModel

# Each indicator rule checks its own field (validators-v3): the applicant settles baselines and targets,
# PaperAid the rest, so each is reported, and owned, separately.
FIELD_RULES = (
    ("FP-025", "unit", "Every indicator has a unit."),
    ("FP-026", "baseline or a plan to set one", "Every outcome indicator has a baseline or a plan to set one."),
    ("FP-027", "target", "Every outcome indicator has a target."),
    ("FP-030", "means of verification", "Every indicator has a source of data."),
    ("FP-031", "frequency", "Every indicator has a measurement frequency."),
    ("FP-032", "responsible role", "Every indicator has a responsible role."),
)
WRITTEN_FIELDS = ("unit", "means of verification", "frequency", "responsible role")  # what the Results Model's writer supplies; baselines and targets are the applicant's


def written_gaps(ind: Indicator) -> list[str]:
    """The indicator fields missing that PaperAid's writer, not the applicant, must supply."""
    return [g for g in _missing(ind) if g in WRITTEN_FIELDS]


def _missing(ind: Indicator) -> list[str]:
    gaps = []
    if not ind.unit.strip():
        gaps.append("unit")
    if ind.level in ("outcome", "goal") and ind.baseline is None and not ind.baseline_plan.strip():
        gaps.append("baseline or a plan to set one")
    if ind.level in ("outcome", "goal") and ind.target is None:
        gaps.append("target")
    if not ind.means_of_verification.strip():
        gaps.append("means of verification")
    if not ind.frequency.strip():
        gaps.append("frequency")
    if not ind.responsible_role.strip():
        gaps.append("responsible role")
    return gaps


def checks(model: ResultsModel | None, spec: ResolvedSpec) -> list[Check]:
    if model is None or not model.goal.statement.strip() or not model.outcomes:
        return [("FP-014", "FAIL", "Build the Results Model: the goal, outcomes, outputs, activities and indicators.")]
    out: list[Check] = [("FP-014", "PASS", "The Results Model has a goal, outcomes, outputs and activities.")]
    outcomes, outputs = {o.id for o in model.outcomes}, {o.id for o in model.outputs}
    results = {model.goal.id, *outcomes, *outputs}
    loose = [a.id for a in model.activities if a.output_id not in outputs]
    out.append(("FP-018", "FAIL" if loose else "PASS", f"Activities without an output: {', '.join(loose)}." if loose else "Every activity leads to an output."))
    loose = [o.id for o in model.outputs if o.outcome_id not in outcomes]
    out.append(("FP-019", "FAIL" if loose else "PASS", f"Outputs without an outcome: {', '.join(loose)}." if loose else "Every output leads to an outcome."))
    measured = {i.result_id for i in model.indicators}
    bare = [o.id for o in model.outcomes if o.id not in measured]
    out.append(("FP-022", "FAIL" if bare else "PASS", f"Outcomes without an indicator: {', '.join(bare)}." if bare else "Every outcome has an indicator."))
    bare = [o.id for o in model.outputs if o.id not in measured]
    out.append(("FP-023", "FAIL" if bare else "PASS", f"Outputs without an indicator: {', '.join(bare)}." if bare else "Every output has an indicator."))
    level_of = {model.goal.id: "goal", **{o: "outcome" for o in outcomes}, **{o: "output" for o in outputs}}
    wrong = [i.id for i in model.indicators if i.result_id not in results or level_of.get(i.result_id) != i.level]
    out.append(("FP-024", "FAIL" if wrong else "PASS", f"Indicators measuring no result, or the wrong level: {', '.join(wrong)}." if wrong else "Each indicator measures a result at its own level."))
    for rid, field, done in FIELD_RULES:
        missing = [i.id for i in model.indicators if field in _missing(i)]
        out.append((rid, "FAIL" if missing else "PASS", f"Missing the {field}: {', '.join(missing)}." if missing else done))
    if spec.flags.get("disaggregation_required"):
        bare = [i.id for i in model.indicators if i.level != "goal" and not i.disaggregation]
        out.append(("FP-029", "FAIL" if bare else "PASS", f"Not disaggregated: {', '.join(bare)}." if bare else "Indicators are disaggregated."))
    months = spec.duration_months
    unscheduled = [a.id for a in model.activities if a.major and (a.start_month is None or a.end_month is None or a.end_month < a.start_month or (months and a.end_month > months))]
    out.append(("FP-036", "FAIL" if unscheduled else "PASS",
                f"Activities with no valid dates{f' within {months} months' if months else ''}: {', '.join(unscheduled)}." if unscheduled else "Every major activity is in the timeline."))
    ownerless = [r.id for r in model.risks if not r.owner_role.strip() or not r.mitigation.strip()]
    out.append(("FP-056", "NEEDS_REVIEW" if ownerless else "PASS", f"Risks without a mitigation or owner: {', '.join(ownerless)}." if ownerless else "Every risk has a mitigation and an owner."))
    for rid, note in (("FP-073", "The logframe is built by PaperAid from the Results Model."), ("FP-074", "The workplan is built from the activities and their months."),
                      ("FP-075", "The M&E table is built from the indicators.")):
        out.append((rid, "PASS", note))
    return out


TO_ADD = "[to be added]"  # a figure only the applicant gives, not entered yet


def logframe(model: ResultsModel) -> list[list[str]]:
    """Level | Result | Indicators | Baseline | Target | Means of verification | Assumptions."""
    rows = [["Level", "Result", "Indicators", "Baseline", "Target", "Means of verification", "Assumptions"]]

    def cells(result_id: str) -> tuple[str, str, str, str]:
        found = [i for i in model.indicators if i.result_id == result_id]
        return (
            "; ".join(f"{i.id}: {i.definition}" for i in found),
            "; ".join(_value(i.baseline, i.unit) or i.baseline_plan or TO_ADD for i in found),
            "; ".join(_value(i.target, i.unit) or TO_ADD for i in found),
            "; ".join(i.means_of_verification for i in found),
        )

    rows.append(["Goal", model.goal.statement, *cells(model.goal.id), "; ".join(model.assumptions)])
    for o in model.outcomes:
        rows.append([f"Outcome {o.id}", o.statement, *cells(o.id), "; ".join(o.assumptions)])
        for p in (p for p in model.outputs if p.outcome_id == o.id):
            rows.append([f"Output {p.id}", p.statement, *cells(p.id), ""])
    return rows


def workplan(model: ResultsModel, months: int | None) -> list[list[str]]:
    """Activity | Owner | one column per quarter (or month for short projects), marked when active."""
    last = months or max((a.end_month or 0 for a in model.activities), default=12) or 12
    step = 1 if last <= 12 else 3
    periods = list(range(1, last + 1, step))
    header = ["Activity", "Responsible", *[f"M{p}" if step == 1 else f"Q{(p - 1) // 3 + 1}" for p in periods]]
    rows = [header]
    for a in model.activities:
        start, end = a.start_month or 0, a.end_month or 0
        marks = ["■" if start and end and start <= p + step - 1 and end >= p else "" for p in periods]
        rows.append([f"{a.id}: {a.statement}", a.owner_role, *marks])
    return rows


def mel_table(model: ResultsModel) -> list[list[str]]:
    rows = [["Indicator", "Result", "Unit", "Baseline", "Target", "Data source", "Frequency", "Responsible", "Disaggregation"]]
    for i in model.indicators:
        rows.append([f"{i.id}: {i.definition}", i.result_id, i.unit, _value(i.baseline, i.unit) or i.baseline_plan or TO_ADD, _value(i.target, i.unit) or TO_ADD,
                     i.means_of_verification, i.frequency, i.responsible_role, ", ".join(i.disaggregation)])
    return rows


def _value(value: float | None, unit: str) -> str:
    if value is None:
        return ""
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return f"{text}%" if unit.strip().lower() in ("%", "percent", "percentage") else text

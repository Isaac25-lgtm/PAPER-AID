"""Academic contract checks. Structural contradictions are code's; suitability remains a review judgement.
No model calls, clinical cutoffs, invented population frames or stock sampling adjustments live here.
Legacy plans have no contract and keep their previous checks and decision hashes.
"""

import hashlib
import json

from app.proposals.models import MethodsContract, MethodVariable, Project, ProposalInputs, ProposalPlan, Variables


def problems(plan: ProposalPlan) -> list[str]:
    contract = plan.methods
    if contract is None:
        return []
    out: list[str] = []
    variables = {v.id: v for v in contract.variables}
    if len(variables) != len(contract.variables):
        out.append("Each methods variable needs its own stable ID; two variables share an ID.")
    rows = {r.objective: r for r in contract.objectives}
    if len(rows) != len(contract.objectives):
        out.append("Each objective needs exactly one methods row; an objective occurs more than once.")
    if set(rows) != set(range(1, len(plan.specific_objectives) + 1)):
        out.append("The methods crosswalk must map each specific objective exactly once.")
    families = {"BINARY_LOGISTIC": "BINARY", "MULTINOMIAL_LOGISTIC": "NOMINAL", "ORDINAL_LOGISTIC": "ORDINAL",
                "POISSON": "COUNT", "NEGATIVE_BINOMIAL": "COUNT"}
    for row in contract.objectives:
        outcome = variables.get(row.outcome_id)
        if row.outcome_id and outcome is None:
            out.append(f"Objective {row.objective} refers to an undefined outcome ({row.outcome_id}).")
        elif outcome is not None:
            if outcome.role not in ("OUTCOME", "EXPLORATORY"):
                out.append(f"Objective {row.objective} uses {outcome.id} as an outcome but its declared role is {outcome.role}.")
            required = families.get(row.estimator)
            # A transformation is a proposal the reviewer must assess, never automatic permission.
            if required and outcome.scale not in (required, "UNKNOWN") and not row.transformation.strip():
                out.append(f"Objective {row.objective}: {row.estimator} requires a {required.lower()} outcome; {outcome.id} is {outcome.scale.lower()}. Specify and justify a transformation or change the estimator.")
        elif row.estimator not in ("DESCRIPTIVE", "THEMATIC", "OTHER"):
            out.append(f"Objective {row.objective} needs an explicitly identified outcome for {row.estimator}.")
        for key in row.predictor_ids:
            if key not in variables:
                out.append(f"Objective {row.objective} refers to an undefined predictor ({key}).")
            elif key == row.outcome_id:
                out.append(f"Objective {row.objective} uses {key} as both its predictor and its outcome.")
            elif variables[key].role == "OUTCOME":
                out.append(f"Objective {row.objective} uses {key} as a predictor although its declared role is OUTCOME; give the intended role explicitly.")
    return list(dict.fromkeys(out))


def context(plan: ProposalPlan, inputs: ProposalInputs | None = None) -> dict:
    """A compact, frozen crosswalk and explicit limits for the existing reviewer and writer.
    Semantic concerns are instructions to read, not regex verdicts or authority to change a student's facts.
    """
    if plan.methods is None:
        return {}
    size = plan.sample_size
    notes = [
        "Assess each objective's outcome, unit, definition, instrument, observation period and estimator together. A statistical test is not proof of an effect or of causation.",
        "Keep descriptive secondary outcomes distinct from the primary inferential outcome. Do not categorise continuous predictors just to use a generic chi-square test; justify thresholds and transformations.",
        "Assess eligible population, sampling-frame coverage, selection units, recruitment, clustering, strata, allocation and weights together. A prevalence-precision formula is not proof of regression power.",
        "An unprovided design effect or non-response allowance remains unknown, never an implicit value of one or zero. Ask for a supplied or explicitly confirmed assumption; do not fabricate it.",
        "Distinguish self-report, records and biological outcomes and their observation windows. Never invent a clinical cutoff, validated instrument, ethics approval, permission or consent exception for minors. Identify unresolved protocol decisions explicitly.",
        "A mediator or moderator requires a justified analysis; otherwise additional factors remain exploratory or adjustment candidates. A framework does not establish causation.",
    ]
    if size.population is not None:
        notes.append(f"Population {size.population} is {plan.methods.population_origin}, not independently verified; a stated source is not verification. Confirm that it counts the eligible frame, not a wider administrative population.")
    return {"version": 1, "crosswalk": plan.methods.model_dump(by_alias=True), "reviewQuestions": notes,
            "samplingAssumptions": {"designEffect": size.design_effect, "nonresponseRate": size.nonresponse_rate,
                                    "sourceStatedByStudent": size.adjustment_source},
            **({"populationDescribedByStudent": inputs.population} if inputs and inputs.population else {})}


def provenance(plan: ProposalPlan) -> list[str]:
    """Submission reminders. No private registry content is searched or independently certified."""
    if plan.methods is None:
        return []
    size = plan.sample_size
    out = []
    if size.population is not None:
        out.append(f"Population used: {size.population:,} ({plan.methods.population_origin.lower().replace('_', ' ')}). "
                   f"Source stated: {size.population_source or 'not supplied'}. Confirm the figure, date and eligibility of the sampling frame before data collection.")
    if size.design_effect is not None or size.nonresponse_rate is not None:
        out.append("Sampling adjustments were supplied by the student, not independently verified. Confirm their rationale: " + (size.adjustment_source or "not supplied") + ".")
    return out


def framework_variables(plan: ProposalPlan) -> Variables:
    if plan.methods is None or plan.study_type not in ("QUANTITATIVE", "MIXED"):
        return plan.variables
    return Variables(independent=[v.label for v in plan.methods.variables if v.role == "PREDICTOR"],
                     dependent=[v.label for v in plan.methods.variables if v.role == "OUTCOME"],
                     intervening=[f"{v.label} ({v.role.lower()})" for v in plan.methods.variables if v.role not in ("PREDICTOR", "OUTCOME")])


def figure_plan(current: ProposalPlan | None, snapshot: ProposalPlan | None) -> ProposalPlan | None:
    """The plan a chapter's framework is drawn from. A plan with the methods contract keeps the one its framework
    section was written from, since its arrows come from analysis rows the text describes. Any other plan is drawn
    from the study as it now stands: the student's own edit of the variables redraws the figure at once and marks the
    section for review, as it always has (owner decision 2026-10-08)."""
    return snapshot if snapshot is not None and snapshot.methods is not None else current


def frame_signature(plan: ProposalPlan) -> str:
    facts = [plan.population, plan.inclusion, plan.sample_size.population, plan.sample_size.population_source,
             plan.methods.population_frame if plan.methods else ""]
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False).encode()).hexdigest()


def frame_confirmed(project: Project) -> bool:
    plan = project.plan
    if plan is None or plan.methods is None or plan.sample_size.population is None:
        return True  # no new frame requirement for legacy plans or an N-free calculation
    return any(a.kind == "FRAME" and a.plan_version == project.plan_version and a.text_sha256 == frame_signature(plan) for a in project.acknowledgments)


def edit_framework(plan: ProposalPlan, variables: Variables) -> MethodsContract:
    """Keep stable IDs for named measurements. A new factor stays undefined until the author supplies its methods.
    Removing a referenced measurement is refused by problems(), rather than silently changing an analysis.
    """
    assert plan.methods is not None
    old = plan.methods.variables
    used: set[str] = set()
    offered: list[MethodVariable] = []
    ids = {v.id for v in old}
    for group, role in ((variables.independent, "PREDICTOR"), (variables.dependent, "OUTCOME"), (variables.intervening, "EXPLORATORY")):
        prior = [v for v in old if v.role == role or role == "EXPLORATORY" and v.role in ("ADJUSTMENT", "MEDIATOR", "MODERATOR")]
        for position, name in enumerate(group):
            match = next((v for v in old if v.id not in used and (v.label == name or f"{v.label} ({v.role.lower()})" == name)), None)
            if match is None and len(group) == len(prior) and prior[position].id not in used and prior[position].label not in group:
                match = prior[position].model_copy(update={"label": name})
            if match is None:
                key = next((f"V{i}" for i in range(1, 100) if f"V{i}" not in ids), None)
                if key is None:
                    raise ValueError("No measurement ID remains.")
                ids.add(key)
                match = MethodVariable(id=key, label=name, role=role, scale="UNKNOWN")
            elif role == "EXPLORATORY" and match.role in ("ADJUSTMENT", "MEDIATOR", "MODERATOR", "EXPLORATORY"):
                pass  # an explicitly declared role is not discarded by the legacy grouping
            else:
                match = match.model_copy(update={"role": role})
            used.add(match.id)
            offered.append(match)
    contract = MethodsContract.model_validate({**plan.methods.model_dump(), "variables": [v.model_dump() for v in offered]})
    if issues := problems(plan.model_copy(update={"methods": contract})):
        raise ValueError(" ".join(issues))
    return contract

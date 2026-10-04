"""Scripted stand-in answers for the works steps (tests and the browser-test backend only). The
reader finds requirements with simple patterns and quotes them exactly; the planner echoes the
skeleton; the writer writes sections near their word target from the brief, citing the first
evidence it is given and using the number tokens it is offered; every review passes. A test can
replace any task through `FakeModels.overrides`."""

import re
from typing import Any

PATTERNS: list[tuple[str, str, str]] = [
    # (key, pattern whose whole match is the quote, unit); group 1 is the number when there is one
    ("limit.words", r"(?:must not exceed|maximum of|no more than|word limit(?: is|:)?)\s*([\d,]+)\s*words", "words"),
    ("limit.pages", r"(?:must not exceed|maximum of|no more than)\s*(\d+)\s*pages", "pages"),
    ("ceiling", r"(?:funding ceiling|maximum grant|up to)\s*(?:is|of|:)?\s*USD\s*([\d,]+)", "USD"),
    ("duration_months", r"(?:duration of|last(?:s)? up to|implementation period of)\s*(\d+)\s*months", "months"),
    ("cost_share", r"cost[- ]share of (?:at least )?(\d+)%", "percent"),
    ("citation_style", r"(?:use|referenced in|referencing style:?)\s*(APA 7|APA 6|Harvard)", ""),
    ("ai_policy", r"(?:generative )?AI (?:tools )?(?:must not|may not|cannot) be used[^.]*", ""),
    ("ai_policy", r"AI (?:tools )?may be used (?:if|provided)[^.]*", ""),
    ("source_policy", r"[Uu]se only the (?:set|required) readings", ""),
]
LINE_KEYS = {"Eligibility:": "eligibility", "Priority:": "priority", "Prohibited:": "prohibited_cost", "Required section:": "section.required",
             "Scoring:": "scoring", "Criterion:": "rubric", "Required reading:": "required_reading", "Box:": "field"}


def read(payload: dict[str, Any]) -> dict[str, Any]:
    found = []
    readings = []
    for source in payload["sources"]:
        text = source["text"]
        for key, pattern, unit in PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                number = float(m.group(1).replace(",", "")) if m.groups() and m.group(1) and m.group(1).replace(",", "").isdigit() else None
                value = m.group(1) if key == "citation_style" else m.group(0)
                found.append({"sourceId": source["id"], "key": key, "value": value, "number": number, "unit": unit, "hard": True, "quote": m.group(0),
                              "location": "", "weight": None, "countsToward": [], "amends": False})
        for line in text.splitlines():
            line = line.strip()
            for prefix, key in LINE_KEYS.items():
                if line.startswith(prefix):
                    rest = line[len(prefix):].strip()
                    weight = re.search(r"\((\d+)%?\)", rest)
                    limit = re.search(r"(\d+) characters", rest)
                    value = re.sub(r"\s*\(\d+%?\)|\s*\(\d+ characters\)", "", rest)
                    found.append({"sourceId": source["id"], "key": key, "value": value, "number": float(limit.group(1)) if limit else float(weight.group(1)) if weight else None,
                                  "unit": "characters" if limit else "", "hard": True, "quote": line, "location": "", "weight": float(weight.group(1)) if weight and not limit else None,
                                  "countsToward": [], "amends": False})
        for m in re.finditer(r"((?:Critically evaluate|Explain|Discuss|Compare and contrast|Analyse|To what extent)[^.?]*[.?])", text):
            found.append({"sourceId": source["id"], "key": "directive", "value": m.group(1), "number": None, "unit": "", "hard": True, "quote": m.group(1),
                          "location": "", "weight": None, "countsToward": [], "amends": False})
        if source["role"] == "READING":
            first = text.strip().splitlines()[0] if text.strip() else source["name"]
            readings.append({"sourceId": source["id"], "title": first[:120], "authors": ["Mugisha, P."], "organisation": "", "year": "2021", "container": "", "doi": ""})
    return {"requirements": found, "unclear": [], "readings": readings}


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload["spec"]
    coverage = [c["id"] for c in spec.get("coverage", [])]
    body = [s["key"] for s in payload["skeleton"] if s["key"].startswith("theme") or s["key"] in ("analysis", "findings", "reflection", "approach", "technical_approach")]
    sections = []
    for s in payload["skeleton"]:
        mine = [c for n, c in enumerate(coverage) if body and body[n % len(body)] == s["key"]]
        heading = f"{s['heading']}: {payload['student']['title'][:40]}" if s["key"].startswith("theme") else s["heading"]
        sections.append({"key": s["key"], "heading": heading, "words": s["words"], "brief": f"Cover {s['heading'].lower()} for this task, using the evidence given.",
                         "criteria": [c["id"] for c in spec.get("scoring", [])][:1] if s is payload["skeleton"][0] else [], "coverage": mine})
    return {"title": payload["student"]["title"], "position": "The evidence supports a qualified answer.", "sections": sections, "questionsForStudent": [], "notes": []}


def results(payload: dict[str, Any]) -> dict[str, Any]:
    months = payload["spec"].get("duration") or 12
    return {
        "goal": {"id": "G1", "statement": "Improved maternal health in the district"},
        "objectives": [{"id": "OBJ1", "statement": "Increase facility deliveries"}, {"id": "OBJ2", "statement": "Strengthen community referral"}],
        "outcomes": [{"id": "O1", "statement": "More mothers deliver at health facilities", "objectiveId": "OBJ1", "assumptions": ["Facilities stay open"]},
                     {"id": "O2", "statement": "Village health teams refer danger signs promptly", "objectiveId": "OBJ2", "assumptions": []}],
        "outputs": [{"id": "OP1", "statement": "Trained village health teams", "outcomeId": "O2"}, {"id": "OP2", "statement": "Functional referral system", "outcomeId": "O1"}],
        "activities": [
            {"id": "A1", "statement": "Train village health teams", "outputId": "OP1", "ownerRole": "Project Manager", "startMonth": 1, "endMonth": 3, "costed": True, "major": True},
            {"id": "A2", "statement": "Set up referral transport", "outputId": "OP2", "ownerRole": "Project Manager", "startMonth": 2, "endMonth": min(6, months), "costed": True, "major": True},
            {"id": "A3", "statement": "Run quarterly reviews", "outputId": "OP2", "ownerRole": "MEL Officer", "startMonth": 3, "endMonth": months, "costed": True, "major": True},
        ],
        "indicators": [
            {"id": "I1", "resultId": "O1", "level": "outcome", "definition": "Share of deliveries at a facility", "unit": "%", "baselinePlan": "District records, month 1",
             "targetDate": "", "disaggregation": ["age"], "meansOfVerification": "HMIS", "frequency": "quarterly", "responsibleRole": "MEL Officer"},
            {"id": "I2", "resultId": "O2", "level": "outcome", "definition": "Referrals within 24 hours", "unit": "%", "baselinePlan": "Baseline survey, month 1",
             "targetDate": "", "disaggregation": [], "meansOfVerification": "Referral registers", "frequency": "quarterly", "responsibleRole": "MEL Officer"},
            {"id": "I3", "resultId": "OP1", "level": "output", "definition": "Village health team members trained", "unit": "people", "baselinePlan": "",
             "targetDate": "", "disaggregation": ["sex"], "meansOfVerification": "Training records", "frequency": "monthly", "responsibleRole": "Project Manager"},
        ],
        "risks": [{"id": "R1", "statement": "Staff turnover", "likelihood": "medium", "impact": "medium", "mitigation": "Train deputies", "ownerRole": "Project Manager"}],
        "assumptions": ["The district supports the project"],
        "budgetLines": [
            {"category": "Training", "description": "Village health team training", "unit": "workshop", "activityIds": ["A1"], "support": False, "role": ""},
            {"category": "Transport", "description": "Referral transport", "unit": "month", "activityIds": ["A2"], "support": False, "role": ""},
            {"category": "Monitoring and evaluation", "description": "Quarterly reviews and data collection", "unit": "review", "activityIds": ["A3"], "support": False, "role": ""},
        ],
    }


def _text(section: dict[str, Any], tokens: list[dict[str, Any]]) -> list[str]:
    words = max(40, int(section.get("words", 150)))
    topic = section["heading"].lower()
    cite = f" ⟦{section['evidence'][0]['id']}⟧" if section.get("evidence") else ""
    sentences = [f"This section sets out {topic} with the care the task asks for.{cite}"]
    fillers = ["It connects each point to the question and to the student's own setting.", "The argument moves from what is known to what it means here.",
               "Each claim is kept within what the confirmed evidence shows.", "The discussion weighs what supports the position against what limits it.",
               "Practical implications follow from the analysis above."]
    total = len(sentences[0].split())
    n = 0
    while total < words * 0.95:
        sentence = fillers[n % len(fillers)]
        sentences.append(sentence)
        total += len(sentence.split())
        n += 1
    if section["key"] in ("budget_narrative", "timeline_budget") and any(t["token"] == "⟦N:budget.total⟧" for t in tokens):
        sentences.append("The budget totals ⟦N:budget.total⟧.")
    half = max(1, len(sentences) // 2)
    return [" ".join(sentences[:half]), " ".join(sentences[half:])] if len(sentences) > 1 else sentences


def draft(payload: dict[str, Any]) -> dict[str, Any]:
    tokens = payload.get("numberTokens", [])
    return {"sections": [{"key": s["key"], "paragraphs": _text(s, tokens), "table": {"caption": "", "rows": []}} for s in payload["sections"]]}


def repair(payload: dict[str, Any]) -> dict[str, Any]:
    out = []
    for s in payload["sections"]:
        text = list(s["text"])
        asked = [i for i in s.get("issues", []) if i.startswith("The student asks:")]
        if asked:
            text.append("This section now addresses the change you asked for.")
        out.append({"key": s["key"], "paragraphs": text, "table": s.get("table") or {"caption": "", "rows": []}})
    return {"sections": out}


def compress(payload: dict[str, Any]) -> dict[str, Any]:
    out = []
    for s in payload["sections"]:
        words = " ".join(s["text"]).split()[: max(10, int(s["targetWords"]))]
        out.append({"key": s["key"], "paragraphs": [" ".join(words).rstrip(".,;") + "."], "table": s.get("table") or {"caption": "", "rows": []}})
    return {"sections": out}


def answer(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task == "w_read":
        return read(payload)
    if task == "w_needs":
        return {"needs": [{"id": "n1", "need": "Evidence on the main question", "kind": "LITERATURE", "query": "maternal health referral uganda"},
                          {"id": "n2", "need": "A current national figure", "kind": "FACT", "query": "maternal mortality uganda 2022"}]}
    if task == "w_plan":
        return plan(payload)
    if task in ("w_plan_review",):
        return {"verdict": "PASS", "rules": [{"rule": r["rule"], "status": "PASS", "note": "Met."} for r in payload.get("rules", [])], "issues": []}
    if task == "w_results":
        return results(payload)
    if task == "w_results_review":
        model = payload["results"]
        labelled = [("goal", model["goal"])] + [("outcome", o) for o in model["outcomes"]] + [("output", o) for o in model["outputs"]]
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met."} for r in payload.get("rules", [])],
                "classified": [{"id": item["id"], "statedAs": level, "reads": level, "note": ""} for level, item in labelled], "issues": [], "reversed": []}
    if task == "w_draft":
        return draft(payload)
    if task == "w_integrity":
        return {"results": [{"key": s["key"], "meaningKept": True, "invented": [], "lockedChanged": [], "note": ""} for s in payload["sections"]]}
    if task == "w_evaluate":
        return {"results": [{"key": s["key"], "verdict": "PASS", "rules": [{"rule": r["rule"], "status": "PASS", "note": "Met."} for r in s["rules"]], "issues": [],
                             "scores": {"fidelity": 92, "quality": 88, "naturalness": 90}} for s in payload["sections"]]}
    if task == "w_repair":
        return repair(payload)
    if task == "w_adjudicate":
        return {"results": [{"key": s["key"], "decision": "PASS", "instruction": ""} for s in payload["sections"]]}
    if task == "w_final":
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met across the document.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": True, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}
    if task == "w_compress":
        return compress(payload)
    raise KeyError(task)

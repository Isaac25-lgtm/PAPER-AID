"""Scripted stand-in for both AI roles, used only by the tests (and the browser-test launcher).

It answers every task in the algorithm with a plausible, deterministic reply: the lead analyses
without raising anything new, plans a generic rewrite, finalises the draft and passes every review;
the writer agrees with the plan and rewrites with `tests.fake_writer`. A test can replace any task
through `overrides[task] = lambda payload: answer`. The app never imports this module."""

import json
from typing import Any

from app.ai.providers import ModelResult, Usage
from app.formatting.guideline import read_guide
from tests import fake_writer

SOURCE_URL = "https://stats.example.org/report-2022"
SOURCE_PAGE = "<html><body><h1>Annual report</h1><p>The report gives the figure for 2022. It covers every district.</p></body></html>"
INSTRUCTION = "Cut filler and stock phrases, replace stacked transitions and vary sentence structure; keep every claim, number and citation."
ABSTRACT = (
    "Background: vaccine uptake among caregivers remains uneven. Methods: a cross-sectional survey of 410 caregivers in Mukono. "
    "Results: distance to the health facility was associated with lower uptake of the vaccine among caregivers in rural parishes."
)
WORK = {
    "doi": "10.1186/s12936-022-0001", "url": "https://doi.org/10.1186/s12936-022-0001", "title": "Vaccine uptake among caregivers in central Uganda",
    "authors": "Okello, J.; Namara, A.; Kato, P.", "year": "2022", "container": "Malaria Journal", "volume": "21", "issue": "3", "pages": "1–10",
    "type": "article", "abstract": ABSTRACT,
}
CROSSREF = {
    "doi": WORK["doi"], "title": "Vaccine Uptake Among Caregivers in Central Uganda", "authors": "Okello, J.; Namara, A.; Kato, P.", "year": "2022",
    "container": "Malaria Journal", "volume": "21", "issue": "3", "pages": "1–10", "type": "journal-article",
}
PLAN = {
    "title": "Determinants of malaria vaccine uptake among caregivers in Mukono District",
    "problem": "Uptake of the malaria vaccine remains below target, and the reasons in Mukono are not known.",
    "purpose": "To establish the determinants of malaria vaccine uptake among caregivers in Mukono District.",
    "specificObjectives": ["To assess the effect of distance on uptake", "To examine caregivers' attitudes towards the vaccine", "To determine the role of health workers in uptake"],
    "questionsKind": "QUESTIONS",
    "researchQuestions": ["How does distance affect uptake?", "What attitudes do caregivers hold?", "What role do health workers play?"],
    "studyType": "QUANTITATIVE", "design": "A cross-sectional survey, because it measures uptake and its determinants at one time.",
    "studyArea": "Mukono District", "population": "Caregivers of children under two", "sampling": "Multi-stage cluster sampling of parishes and households.",
    "sampleSize": {"method": "YAMANE", "population": 2400, "populationSource": "", "margin": 0.05, "confidence": 95, "proportion": 0.5, "stated": None, "rationale": ""},
    "inclusion": "Caregivers of children aged 6-23 months living in the district for six months.",
    "variables": {"independent": ["distance", "attitudes", "health worker advice"], "dependent": ["vaccine uptake"], "intervening": []},
    "alignment": [
        {"objective": 1, "data": "Distance and uptake", "collection": "Questionnaire", "analysis": "Chi-square test"},
        {"objective": 2, "data": "Attitude scores", "collection": "Questionnaire", "analysis": "Descriptive statistics and regression"},
        {"objective": 3, "data": "Advice received", "collection": "Questionnaire", "analysis": "Logistic regression"},
    ],
    "theory": "The Health Belief Model, because uptake depends on perceived barriers and cues to action.",
    "scope": "Mukono District, 2026, determinants of uptake.",
    "timelineMonths": 6, "gaps": [], "questionsForStudent": [],
}


class FakeModels:
    name = "fake"

    def __init__(self) -> None:
        self.overrides: dict[str, Any] = {}
        self.tasks: list[str] = []
        self.requests: list[str] = []
        self.tokens = (0, 0)  # (input, output) reported per call; set with real prices to create costs
        self.refuse: set[str] = set()  # tasks answered with a refusal
        self.truncate: set[str] = set()  # tasks whose answers are always cut off by the output limit
        self.opened: list[str] = [SOURCE_URL]  # the pages a fake web search "opened"
        self.sent_queries: list[str] | None = None  # queries the fake search "sent" (default: the suggested one)
        self.pages: dict[str, str] = {SOURCE_URL: SOURCE_PAGE}  # what reading each source page returns
        self.abstracts: dict[str, str] = {}  # what the abstract lookup returns for a source URL
        self.works: list[dict[str, str]] = [dict(WORK)]  # what the scholarly index returns for any query
        self.crossref: dict[str, dict[str, str]] = {WORK["doi"]: dict(CROSSREF)}  # registered details by DOI
        self.searched: list[str] = []  # queries sent to the scholarly index
        self.crossref_found: list[dict[str, str]] = []  # what a bibliographic search of any reference returns
        self.retracted: set[str] = set()  # DOIs OpenAlex reports as retracted
        self.dois: dict[str, str] = {}  # DOIs looked up for PubMed/PMC pages

    def json(self, task: str, model: str, system: str, payload: dict[str, Any], schema: dict[str, Any], max_tokens: int) -> ModelResult:
        self.tasks.append(task)
        self.requests.append(task + json.dumps(payload, sort_keys=True))
        usage = Usage(self.tokens[0], self.tokens[1], 0, 1)
        if task in self.refuse:
            return ModelResult(text="", usage=usage, provider="fake", model=model, stop="refusal")
        if task in self.truncate:
            return ModelResult(text="{", usage=usage, provider="fake", model=model, stop="max_tokens")
        answer = self.overrides[task](payload) if task in self.overrides else self.default(task, payload)
        return ModelResult(text=json.dumps(answer), usage=usage, provider="fake", model=model)

    def search_json(
        self, task: str, model: str, system: str, payload: dict[str, Any], schema: dict[str, Any], max_tokens: int, max_searches: int
    ) -> ModelResult:
        result = self.json(task, model, system, payload, schema, max_tokens)
        result.usage.search_calls = min(1, max_searches)
        result.sources = list(self.opened)
        result.queries = list(self.sent_queries) if self.sent_queries is not None else [payload["query"]]
        return result

    @staticmethod
    def default(task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if task == "analyse":  # confirms every PaperAid signal; returns only passages that have one
            return {
                "blocks": [
                    {
                        "id": b["id"], "riskBand": "low", "reasons": [], "explanation": "", "suggestion": "", "excerpt": "",
                        "confirmed": [s["rule"] for s in b["signals"]], "rejected": [], "preserve": False, "risk": "",
                    }
                    for b in payload["blocks"]
                    if b["signals"]
                ]
            }
        if task == "academic":  # one rewordable finding on the first passage of each batch
            first = payload["passages"][0] if payload["passages"] else None
            findings = []
            if first:
                excerpt = " ".join(first["text"].split()[:8])
                findings.append({"id": first["id"], "category": "ACADEMIC", "code": "VAGUE_WORDING", "severity": "minor", "excerpt": excerpt, "explanation": "The claim is too general to check.", "suggestion": "Say what, where and when."})
            return {"findings": findings}
        if task == "plan":
            return {"blocks": [{"id": p["id"], "action": "rewrite", "instruction": INSTRUCTION, "preserve": "the student's claims"} for p in payload["passages"]]}
        if task == "critique":
            return {"blocks": [{"id": p["id"], "agree": True, "comment": ""} for p in payload["passages"]], "overall": ""}
        if task == "finalise":
            return {"blocks": [{"id": p["id"], **p["draft"]} for p in payload["passages"]]}
        if task == "refine":
            return {"blocks": [{"id": b["id"], "text": fake_writer.rewrite(b["text"])} for b in payload["blocks"]]}
        if task == "review":
            return {"results": [{"id": p["id"], "grade": "PASS", "issues": [], "note": "", "riskBand": "low"} for p in payload["pairs"]]}
        if task == "repair":
            return {"blocks": [{"id": b["id"], "text": b["original"]} for b in payload["blocks"]]}
        if task == "claims":  # the first sentence of the first passages that mention a year
            found = []
            for p in payload["passages"]:
                sentence = p["text"].split(". ")[0].strip()
                if any(str(y) in sentence for y in range(1990, 2030)) and len(found) < payload["limit"]:
                    found.append({"id": p["id"], "claim": sentence, "cited": "(" in sentence, "query": "mobile money accounts Uganda", "importance": "high"})
            return {"claims": found}
        if task == "research":
            source = {
                "url": SOURCE_URL, "title": "Annual report", "publisher": "Statistics office", "published": "2022", "access": "FULL_TEXT",
                "passage": "The report gives the figure for 2022.", "scope": "Uganda, 2022", "supports": "SUPPORTED",
            }
            return {"support": "SUPPORTED", "note": "The report states the same figure.", "sources": [source]}
        if task == "verify":
            return {"results": [{"id": c["id"], "support": "SUPPORTED", "note": "The passage matches."} for c in payload["claims"]]}
        if task == "redraft":  # rewrites each paragraph and merges the first two, to exercise restructuring
            answer = []
            for g in payload["groups"]:
                paragraphs = [fake_writer.rewrite(p) for p in g["paragraphs"]]
                if len(paragraphs) > 1:
                    paragraphs = [paragraphs[0] + " " + paragraphs[1], *paragraphs[2:]]
                answer.append({"id": g["id"], "paragraphs": paragraphs})
            return {"groups": answer}
        if task == "redraft_fix":
            return {"groups": [{"id": g["id"], "paragraphs": g["original"]} for g in payload["groups"]]}
        if task == "spec_plan":
            return read_guide(payload["guide"])
        if task == "spec_critique":
            return {"items": [], "overall": "The draft matches the guide."}
        if task == "spec_finalise":
            return payload["draft"]
        if task == "spec_review":
            return {"pass": True, "problems": []}
        if task == "spec_fix":
            return payload["spec"]
        return FakeModels.proposal(task, payload)

    @staticmethod
    def proposal(task: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Proposal steps: one scholarly need and one web need; a coherent plan; briefs citing the
        first evidence item; drafts in the future tense that cite it; every review passes."""
        if task == "p_needs":
            return {
                "needs": [
                    {"id": "n1", "need": "Determinants of vaccine uptake among caregivers", "kind": "LITERATURE", "query": "malaria vaccine uptake caregivers"},
                    {"id": "n2", "need": "The latest national figure", "kind": "FACT", "query": "malaria burden Uganda 2022"},
                ]
            }
        if task == "p_extract":
            return {"findings": [{"work": payload["works"][0]["id"], "statement": "Distance was associated with lower uptake among rural caregivers.", "passage": "distance to the health facility was associated with lower uptake of the vaccine", "scope": "Mukono, caregivers"}]}
        if task == "p_search":
            return {"findings": [{"url": SOURCE_URL, "title": "Annual report", "publisher": "Statistics office", "published": "2022", "access": "FULL_TEXT", "statement": "The report gives the national figure for 2022.", "passage": "The report gives the figure for 2022.", "scope": "Uganda, 2022"}]}
        if task in ("p_plan",):
            return dict(PLAN)
        if task == "p_critique":
            return {"items": [], "overall": "Sound."}
        if task == "p_finalise":
            return payload["draft"]
        if task == "p_brief":
            first = payload["evidence"][0]["id"] if payload["evidence"] else None

            def cites(key: str) -> bool:
                return first is not None and (key in ("background", "problem") or key.startswith("empirical"))

            return {"sections": [{"key": s["key"], "points": [f"Explain {s['heading']}."], "evidence": [first] if cites(s["key"]) else []} for s in payload["sections"]]}
        if task in ("p_draft", "p_fix"):
            out = []
            for s in payload["sections"]:
                if task == "p_fix":
                    out.append({"key": s["key"], "paragraphs": s["text"], "table": s["table"]})
                    continue
                cite = f" ⟦{s['evidence'][0]['id']}⟧" if s["evidence"] else ""
                table = {"caption": "Work plan", "rows": [["Activity", "Months"], ["Data collection", "Month 3"]]} if s["table"] else {"caption": "", "rows": []}
                out.append({"key": s["key"], "paragraphs": [f"This section sets out {s['heading'].lower()} for the study.{cite}", "The study will follow the approved plan."], "table": table})
            return {"sections": out}
        if task == "p_review":
            return {"results": [{"key": s["key"], "grade": "PASS", "issues": [], "note": ""} for s in payload["sections"]]}
        if task == "p_readiness":
            return {"items": [{"id": q["id"], "status": "PASS", "note": "Present.", "where": ""} for q in payload["questions"]], "consistency": []}
        if task == "p_audit":
            items = [{"id": q["id"], "status": "NEEDS_REVIEW", "note": "Partly.", "where": ""} for qs in payload["vetting"].values() for q in qs]
            first = payload["paragraphs"][0]["id"] if payload["paragraphs"] else ""
            return {"items": items, "findings": [{"where": first, "kind": "ALIGNMENT", "severity": "major", "issue": "Objective 2 has no matching question.", "suggestion": "Add a question for it."}]}
        raise KeyError(f"no fake answer for {task}")

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
        raise KeyError(f"no fake answer for {task}")

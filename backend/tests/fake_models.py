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

INSTRUCTION = "Cut filler and stock phrases, replace stacked transitions and vary sentence structure; keep every claim, number and citation."


class FakeModels:
    name = "fake"

    def __init__(self) -> None:
        self.overrides: dict[str, Any] = {}
        self.tasks: list[str] = []
        self.requests: list[str] = []

    def json(self, task: str, model: str, system: str, payload: dict[str, Any], schema: dict[str, Any], max_tokens: int) -> ModelResult:
        self.tasks.append(task)
        self.requests.append(task + json.dumps(payload, sort_keys=True))
        answer = self.overrides[task](payload) if task in self.overrides else self.default(task, payload)
        return ModelResult(text=json.dumps(answer), usage=Usage(0, 0, 0, 1), provider="fake", model=model)

    @staticmethod
    def default(task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if task == "analyse":
            return {"blocks": [{"id": b["id"], "riskBand": "low", "reasons": [], "explanation": "", "suggestion": "", "excerpt": ""} for b in payload["blocks"]]}
        if task == "plan":
            return {"blocks": [{"id": p["id"], "action": "rewrite", "instruction": INSTRUCTION, "preserve": "the student's claims"} for p in payload["passages"]]}
        if task == "critique":
            return {"blocks": [{"id": p["id"], "agree": True, "comment": ""} for p in payload["passages"]], "overall": ""}
        if task == "finalise":
            return {"blocks": [{"id": p["id"], **p["draft"]} for p in payload["passages"]]}
        if task == "refine":
            return {"blocks": [{"id": b["id"], "text": fake_writer.rewrite(b["text"])} for b in payload["blocks"]]}
        if task == "review":
            return {"results": [{"id": p["id"], "pass": True, "issues": [], "note": ""} for p in payload["pairs"]]}
        if task == "repair":
            return {"blocks": [{"id": b["id"], "text": b["original"]} for b in payload["blocks"]]}
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

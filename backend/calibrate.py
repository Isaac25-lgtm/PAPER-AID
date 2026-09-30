r"""Calibration harness for the AI-likeness score (plan step M1, owner go-ahead 2026-09-29).

Runs PaperAid's real writing-pattern check (rules, then both checkers) over labelled papers and
compares score formulas. Paid model calls, bounded by --budget-usd; answers are saved in --cache so
a repeat run pays nothing. Prints numbers only: never paper text.

    FOLDER/human/*.docx|pdf   papers known to be written without AI
    FOLDER/ai/*.docx|pdf      papers known to be AI-written
    FOLDER/mixed/*.docx|pdf   (optional) partly AI-written

    .venv\Scripts\python.exe calibrate.py FOLDER --budget-usd 20

Papers are split into a development half and a test half by a fixed hash of the file name. A
formula is chosen on the development half (the one catching most AI papers while rating at most
--max-false-high of human papers HIGH) and then reported on the test half, as Codex required: a
formula must never be judged on the papers it was chosen with. A small set is a pilot, not proof.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.ai.orchestration import AIRunner, current_engine
from app.analysis import signals
from app.core.config import Settings
from app.documents.docx_io import read_docx
from app.documents.pdf_io import read_pdf
from app.jobs.models import ModelCall

LABELS = ("human", "ai", "mixed")
# (rules, first checker, second checker): the current formula first
FORMULAS = {"current 50/25/25": (0.5, 0.25, 0.25), "25/37.5/37.5": (0.25, 0.375, 0.375), "models only 0/50/50": (0.0, 0.5, 0.5)}
LOW, HIGH = 0.15, 0.32  # the current band limits (signals.band_for)


class FileCache:
    """Saved model answers, keyed as the pipeline keys them, so a repeat run replays them free."""

    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> str | None:
        path = self.folder / f"{key}.json"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, key: str, text: str) -> None:
        (self.folder / f"{key}.json").write_text(text, encoding="utf-8")


def split_of(name: str) -> str:
    return "dev" if int(hashlib.sha256(name.encode()).hexdigest(), 16) % 2 == 0 else "test"


def measure(path: Path, settings: Settings, cache: FileCache, budget: float, spent: list[float]) -> dict:
    data = path.read_bytes()
    model = read_pdf(data, settings.max_pdf_pages) if path.suffix.lower() == ".pdf" else read_docx(data)
    found = signals.scan(model)
    passages = [
        {"id": s.block.id, "section": s.block.section or "Body", "sectionType": s.kind, "text": s.block.masked or s.block.text, "signals": s.evidence()}
        for s in found.blocks
    ]
    before = spent[0]

    def record(call: ModelCall) -> None:
        spent[0] += call.cost_usd

    runner = AIRunner(settings, record, lambda: spent[0] - before, budget, cache=cache, engine=current_engine(settings))
    judged, seen = runner.analyse(passages, model.outline(), found.evidence())
    parts = []
    for s in found.blocks:
        judgment = judged.get(s.block.id)
        if judgment is None or s.block.id not in seen or len(judgment.bands) != 2:
            continue
        dropped = {h.rule for h in s.hits} & set(judgment.answer.rejected)
        if dropped:  # as the pipeline does: signals both checkers rejected no longer count
            s.hits = [h for h in s.hits if h.rule not in dropped]
            s.rescore()
        first, second = (signals.MODEL_SCORE[b] for b in judgment.bands)
        parts.append((s.block.words, s.score, first, second, judgment.bands))
    words = sum(w for w, *_ in parts)
    complete = bool(found.blocks) and len(seen) == len(found.blocks)
    scores = {
        name: int(sum(w * (a * rule + b * first + c * second) for w, rule, first, second, _ in parts) / words * 100 + 1e-9) if words else None
        for name, (a, b, c) in FORMULAS.items()
    }
    return {
        "passages": len(found.blocks),
        "judged": len(parts),
        "complete": complete,
        "words": words,
        "ruleMean": round(sum(w * rule for w, rule, *_ in parts) / words, 4) if words else None,
        "disagreeLowHigh": sum(1 for *_, bands in parts if {"low", "high"} <= set(bands)),
        "scores": scores,
        "spendUsd": round(spent[0] - before, 4),
    }


def rates(rows: list[dict], name: str) -> dict:
    out = {}
    for label in LABELS:
        values = [r["scores"][name] for r in rows if r["label"] == label and r["complete"] and r["scores"][name] is not None]
        if values:
            out[label] = {
                "n": len(values),
                "mean": round(sum(values) / len(values), 1),
                "high": round(sum(v >= HIGH * 100 for v in values) / len(values), 2),
                "moderateOrHigh": round(sum(v >= LOW * 100 for v in values) / len(values), 2),
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--budget-usd", type=float, required=True, help="the most this run may spend on AI in total")
    parser.add_argument("--cache", type=Path, default=Path(".calibration-cache"))
    parser.add_argument("--max-false-high", type=float, default=0.05, help="the largest share of human papers a chosen formula may rate HIGH")
    args = parser.parse_args()
    settings = Settings()
    cache = FileCache(args.cache)
    spent = [0.0]
    rows = []
    for label in LABELS:
        for path in sorted((args.folder / label).glob("*")):
            if path.suffix.lower() not in (".docx", ".pdf"):
                continue
            remaining = args.budget_usd - spent[0]
            if remaining <= 0.05:
                print(f"Budget reached after {len(rows)} papers.", file=sys.stderr)
                break
            result = measure(path, settings, cache, remaining, spent)
            rows.append({"paper": hashlib.sha256(path.name.encode()).hexdigest()[:10], "label": label, "split": split_of(path.name), **result})
            print(f"{label:6} {rows[-1]['split']:4} judged {result['judged']}/{result['passages']} scores {result['scores']} ${result['spendUsd']}", file=sys.stderr)
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    by_formula = {name: {"dev": rates(dev, name), "test": rates(test, name)} for name in FORMULAS}
    eligible = [n for n, r in by_formula.items() if r["dev"].get("human", {}).get("high", 1.0) <= args.max_false_high and "ai" in r["dev"]]
    chosen = max(eligible, key=lambda n: by_formula[n]["dev"]["ai"]["moderateOrHigh"], default=None)
    print(json.dumps({
        "papers": len(rows),
        "incomplete": sum(1 for r in rows if not r["complete"]),
        "spendUsd": round(spent[0], 2),
        "formulas": by_formula,
        "chosenOnDev": chosen,
        "testOfChosen": by_formula[chosen]["test"] if chosen else None,
        "caution": "A pilot: too few papers to establish false-positive rates. The test half was not used to choose.",
        "rows": rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

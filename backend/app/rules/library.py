"""The rule files (rulebook v1.0) as data: one file per service plus the shared rules. Validators
live in code (app.rules.validators) and are referenced by id; rule definitions never contain code.

Released rule files never change, like released prompts (`released.json`, enforced by a test): a
change is a new version of the file, and each job runs with the rules version it was priced with."""

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"
VERSION = "rules-v1"
FILES = {"SHARED": "shared-v1", "CONCEPT_NOTE": "concept-note-v1", "COURSEWORK": "coursework-v1", "FUNDING_PROPOSAL": "funding-v1"}
VALIDATORS_VERSION = "validators-v1"  # bumped whenever a validator's behaviour changes
RENDER_PROFILE_VERSION = "render-v1"  # the Word layout the documents are exported with


@cache
def load(name: str) -> dict[str, Any]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def book(kind: str) -> dict[str, Any]:
    return load(FILES[kind])


def shared() -> dict[str, Any]:
    return load(FILES["SHARED"])


def rules_for(kind: str) -> list[dict[str, Any]]:
    """The shared rules and the service's own, in rulebook order."""
    return [*shared()["rules"], *book(kind)["rules"]]


def content_hashes() -> dict[str, str]:
    """What a quote freezes about the rules: each file's hash and the validator and render versions."""
    out = {f"rules:{name}": hashlib.sha256((DATA / f"{name}.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16] for name in FILES.values()}
    out["validators"] = VALIDATORS_VERSION
    out["render"] = RENDER_PROFILE_VERSION
    return out


def applies(rule: dict[str, Any], facts: dict[str, Any]) -> bool:
    """`applies_if` is a flat condition: a list means "one of", a boolean means "equals"; `variant`
    and the directive groups are matched against the facts' lists. Missing facts count as false."""
    for key, wanted in rule.get("applies_if", {}).items():
        have = facts.get(key)
        if key == "directive_any":
            if not set(wanted) & set(facts.get("directive_groups", [])):
                return False
        elif isinstance(wanted, list):
            values = have if isinstance(have, list) else [have]
            if not set(values) & set(wanted):
                return False
        elif bool(have) != bool(wanted):
            return False
    return True


def section_rules(rules: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Semantic rules judged on one section ("theme*" matches every theme)."""
    out = []
    for rule in rules:
        if rule["check"]["validator"] != "semantic":
            continue
        for target in rule.get("sections", []):
            if target == "*" or target == key or (target.endswith("*") and key.startswith(target[:-1])):
                out.append(rule)
                break
    return out


def scoped_rules(rules: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    """Semantic rules judged on the whole document, the plan, or the Results Model."""
    return [r for r in rules if r["check"]["validator"] == "semantic" and scope in r.get("sections", [])]

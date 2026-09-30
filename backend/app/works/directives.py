"""The command-word engine (rulebook §13.3-13.4): which directives a question uses, their groups,
and the parts of a compound question, each of which must be answered (CW-003)."""

import re

from app.rules import library


def lexicon() -> dict[str, dict]:
    return library.book("COURSEWORK")["directives"]


def find(text: str) -> list[str]:
    """Directive ids in the order they appear. The longest phrase wins ("critically evaluate" over
    "evaluate"); a phrase counts only as whole words."""
    lowered = " " + " ".join(re.findall(r"[a-z']+", text.lower())) + " "
    hits: list[tuple[int, int, str]] = []
    for directive, entry in lexicon().items():
        for phrase in entry["phrases"]:
            for m in re.finditer(re.escape(" " + phrase + " "), lowered):
                hits.append((m.start(), -len(phrase), directive))
    hits.sort()
    out: list[str] = []
    covered_until = -1
    for start, negative_length, directive in hits:
        if start < covered_until:
            continue  # inside a longer phrase already taken
        covered_until = start - negative_length
        out.append(directive)
    return out


def groups(ids: list[str]) -> list[str]:
    out: list[str] = []
    for directive in ids:
        for group in lexicon().get(directive, {}).get("groups", []):
            if group not in out:
                out.append(group)
    return out


def expectation(directive: str) -> str:
    return lexicon().get(directive, {}).get("expectation", "")


def clauses(question: str) -> list[tuple[str, str]]:
    """A compound question split at each directive: [(directive id, the clause it governs)].
    "Explain the causes of X and critically evaluate two responses" gives two parts."""
    text = " ".join(question.split())
    ids = find(text)
    if len(ids) <= 1:
        return [(ids[0] if ids else "", text)] if text else []
    phrases = sorted({p for d in ids for p in lexicon()[d]["phrases"]}, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")\b", re.IGNORECASE)
    starts = [m.start() for m in pattern.finditer(text)]
    parts = [text[a:b].strip(" ,;:.") for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]
    parts = [re.sub(r"\s+(and|then)$", "", p, flags=re.IGNORECASE) for p in parts if p]
    out = []
    for part in parts:
        found = find(part)
        out.append((found[0] if found else "", part))
    return out

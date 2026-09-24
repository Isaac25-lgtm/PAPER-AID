"""Locks citations, quotations and links behind ⟦Pn⟧ tokens before rewriting, and checks that
a rewrite kept every locked item and every number exactly."""

import re
from collections import Counter

TOKEN = re.compile(r"⟦([XP]\d+)⟧")

_PROTECTED = [
    re.compile(r"https?://[^\s)\]]+[^\s.,;:)\]]|doi:\s*\S+[^\s.,;:]|www\.[^\s)\]]+[^\s.,;:)\]]", re.I),
    re.compile(r"\"[^\"]{3,}\"|“[^”]{3,}”"),
    re.compile(r"\([^()]*?\b(?:1[89]\d{2}|20\d{2})[a-z]?\b[^()]*\)"),
    re.compile(r"\b[A-Z][\w'’-]+(?:\s+(?:and|&)\s+[A-Z][\w'’-]+|\s+et al\.)?\s+\((?:1[89]\d{2}|20\d{2})[a-z]?(?:,[^)]*)?\)"),
    re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]"),
]
_NUMBER = re.compile(r"(?<![\w⟦])\d[\d,]*(?:\.\d+)?")
_CITATION_LIKE = re.compile(r"\((?:[^()]*?\b(?:1[89]\d{2}|20\d{2})\b[^()]*)\)|\[\d+\]")


def mask(text: str) -> tuple[str, dict[str, str]]:
    """Replace protected spans with ⟦Pn⟧ tokens. Returns masked text and token → original map."""
    spans: list[tuple[int, int]] = []
    for pattern in _PROTECTED:
        for m in pattern.finditer(text):
            if not any(m.start() < end and start < m.end() for start, end in spans):
                spans.append((m.start(), m.end()))
    spans.sort()
    out, originals, cursor = [], {}, 0
    for i, (start, end) in enumerate(spans, start=1):
        key = f"P{i}"
        out.append(text[cursor:start])
        out.append(f"⟦{key}⟧")
        originals[key] = text[start:end]
        cursor = end
    out.append(text[cursor:])
    return "".join(out), originals


def unmask(text: str, originals: dict[str, str]) -> str:
    return TOKEN.sub(lambda m: originals.get(m.group(1), m.group(0)) if m.group(1).startswith("P") else m.group(0), text)


def numbers(text: str) -> Counter[str]:
    visible = TOKEN.sub(" ", text)
    return Counter(n.replace(",", "") for n in _NUMBER.findall(visible))


def check_rewrite(original_masked: str, revised_masked: str) -> list[str]:
    """Deterministic preservation checks. Returns problems; empty means the rewrite is safe to patch."""
    problems = []
    before_tokens = Counter(TOKEN.findall(original_masked))
    after_tokens = Counter(TOKEN.findall(revised_masked))
    missing = before_tokens - after_tokens
    extra = after_tokens - before_tokens
    if missing:
        problems.append(f"locked item removed: {', '.join(sorted(missing))}")
    if extra:
        problems.append(f"locked item duplicated or invented: {', '.join(sorted(extra))}")
    if numbers(original_masked) != numbers(revised_masked):
        problems.append("a number was added, removed or changed")
    visible_after = TOKEN.sub(" ", revised_masked)
    if _CITATION_LIKE.search(visible_after):
        problems.append("a new citation appeared outside the locked citations")
    if not revised_masked.strip():
        problems.append("the rewrite is empty")
    return problems

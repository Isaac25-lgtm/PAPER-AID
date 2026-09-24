"""Test stand-in for the writer model: conservative, meaning-preserving edits (filler, stock
phrases, stacked hedges) so tests exercise real rewrites without calling a provider. Never
imported by the app."""

import re

from app.analysis.signals import ADDITIVE, sentences

# (pattern, replacement). Applied case-insensitively; sentence capitalisation is repaired after.
PHRASES: list[tuple[str, str]] = [
    (r"\bit is important to note that\s+", ""),
    (r"\bit is worth noting that\s+", ""),
    (r"\bit goes without saying that\s+", ""),
    (r"\bit could possibly be argued that this may,? to some extent,? suggest that\b", "this suggests that"),
    (r"\bit could be argued that\s+", ""),
    (r"\bcould possibly\b", "could"),
    (r"\bmay,? to some extent,?\s", "may "),
    (r",?\s*in today's (?:fast-paced world|digital age|world|society)\b", ""),
    (r",?\s*in this day and age\b", ""),
    (r"\bplays a (?:crucial|vital|key) role in\b", "shapes"),
    (r"\bplays a significant role in\b", "strongly influences"),
    (r"\bplays an? (?:crucial|vital|key|significant|important) role(?=[.;,])", "matters"),
    (r"\bhas become a significant part of\b", "is now part of"),
    (r"\bhas become an integral part of\b", "is now central to"),
    (r"\ba significant part of\b", "a large part of"),
    (r"\bhighlights the significance of\b", "shows the importance of"),
    (r"\bunderscores the importance of\b", "shows the importance of"),
    (r"\bdelves? into\b", "examines"),
    (r"\bsheds? light on\b", "clarifies"),
    (r"\ba myriad of\b", "many"),
    (r"\bin the realm of\b", "in"),
    (r"\bin order to\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\ba large number of\b", "many"),
    (r"\bat the end of the day,?\s*", ""),
    (r"\blast but not least,?\s*", "finally, "),
    (r"\bstudies have shown that\b", "studies show that"),
    (r"\butili[sz]e\b", "use"),
    (r"\butili[sz]es\b", "uses"),
    (r"\butili[sz]ed\b", "used"),
]
_OPENERS = re.compile(r"^(in conclusion|to conclude|to sum up),?\s+", re.I)


def _capitalise_sentences(text: str) -> str:
    def fix(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    text = re.sub(r"(^|[.!?]\s+)([a-z])", fix, text)
    return text


def _tidy(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    return _capitalise_sentences(text.strip())


def rewrite(masked: str) -> str:
    """Rewrite one block's masked text. Tokens (⟦X1⟧, ⟦P1⟧) and digits are never touched."""
    out = []
    additive_seen = 0
    for sentence in sentences(masked):
        s = sentence
        for pattern, replacement in PHRASES:
            s = re.sub(pattern, replacement, s, flags=re.I)
        s = _OPENERS.sub("", s)
        m = ADDITIVE.match(s)
        if m:
            additive_seen += 1
            if additive_seen >= 2:  # keep the first additive transition, drop the stacked ones
                s = s[m.end():].lstrip(" ,")
        out.append(s)
    result = _tidy(" ".join(out))
    return result if result != _tidy(masked) else masked

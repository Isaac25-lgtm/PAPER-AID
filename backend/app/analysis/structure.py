"""Formatting findings code can establish exactly, and the count of what refinement protects.
No model is involved: these are facts about the document's structure."""

import re

from app.documents import protect
from app.documents.model import DocumentModel
from app.jobs.models import Finding, ProtectedSummary

CAPTION = re.compile(r"^\s*(table|figure|fig\.)\s+(\d+)", re.I)
URL = protect._PROTECTED[0]
QUOTE = protect._PROTECTED[1]
CITATIONS = protect._PROTECTED[2:]


def _finding(n: int, block_id: str, section: str, reason: str, excerpt: str, explanation: str, suggestion: str) -> Finding:
    return Finding(
        id=f"fmt-{n}",
        block_id=block_id,
        section=section or "Body",
        reason=reason,  # type: ignore[arg-type]
        severity="minor",
        excerpt=excerpt[:200],
        explanation=explanation,
        suggestion=suggestion,
        category="FORMATTING",
        safe=False,  # fixed by Academic formatting, never by rewriting
    )


def formatting_findings(model: DocumentModel, limit: int = 20) -> list[Finding]:
    found: list[Finding] = []
    last_level = 0
    captions: dict[str, list[int]] = {}
    for block in model.blocks:
        if len(found) >= limit:
            break
        if block.detected_heading:
            found.append(
                _finding(
                    len(found) + 1, block.id, block.section, "HEADING_AS_TEXT", block.text,
                    "This heading is typed as bold or enlarged text rather than a heading style, so it will not appear in a table of contents.",
                    "Apply a Word heading style, or choose Academic formatting to convert it.",
                )
            )
        if block.kind == "heading" and block.level:
            if last_level and block.level > last_level + 1:
                found.append(
                    _finding(
                        len(found) + 1, block.id, block.section, "HEADING_LEVEL_SKIP", block.text,
                        f"This heading jumps from level {last_level} to level {block.level}, skipping a level.",
                        f"Make it a level {last_level + 1} heading, or add the missing level above it.",
                    )
                )
            last_level = block.level
        match = CAPTION.match(block.text) if block.kind in ("caption", "paragraph") else None
        if match:
            kind = "Figure" if match.group(1).lower().startswith("fig") else "Table"
            numbers = captions.setdefault(kind, [])
            number = int(match.group(2))
            expected = (numbers[-1] + 1) if numbers else 1
            if number != expected and number not in numbers:
                found.append(
                    _finding(
                        len(found) + 1, block.id, block.section, "CAPTION_NUMBERING", block.text,
                        f"{kind} {number} follows {kind} {numbers[-1] if numbers else 'none'}; captions should be numbered in order.",
                        f"Renumber it {kind} {expected}, and update any references to it in the text.",
                    )
                )
            elif number in numbers:
                found.append(
                    _finding(
                        len(found) + 1, block.id, block.section, "CAPTION_NUMBERING", block.text,
                        f"{kind} {number} is used twice.", "Give each table and figure its own number.",
                    )
                )
            numbers.append(number)
    return found


def protected_summary(model: DocumentModel) -> ProtectedSummary:
    """Counted over the prose refinement may touch: what every rewrite must keep exactly."""
    numbers = citations = quotations = links = items = 0
    for block in model.blocks:
        if block.kind not in ("paragraph", "list_item", "quote", "caption"):
            continue
        text = block.text
        links += len(URL.findall(text))
        quotations += len(QUOTE.findall(text))
        citations += sum(len(p.findall(text)) for p in CITATIONS)
        numbers += sum(protect.numbers(text).values())
        items += len(block.locked)
    return ProtectedSummary(numbers=numbers, citations=citations, quotations=quotations, links=links, word_items=items)

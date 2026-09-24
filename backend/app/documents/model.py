import re
from typing import Literal

from pydantic import BaseModel

BlockKind = Literal["title", "heading", "paragraph", "list_item", "table_cell", "caption", "reference", "quote"]

# Kinds that count toward the AI-likeness estimate and may be refined.
PROSE_KINDS = {"paragraph", "list_item"}


class Block(BaseModel):
    """One paragraph-level unit of the paper, with a stable ID derived from source order."""

    id: str
    kind: BlockKind
    level: int | None = None
    section: str = ""
    text: str
    masked: str | None = None  # text with ⟦Xn⟧ tokens for locked segments; None when not editable
    editable: bool = False
    detected_heading: bool = False  # a heading typed as bold body text rather than a Heading style
    locked: list[str] = []  # display text of each ⟦Xn⟧ segment, in order

    def readable(self, masked: str) -> str:
        """Masked text with ⟦Xn⟧ tokens replaced by what the reader sees in Word."""
        return re.sub(r"⟦X(\d+)⟧", lambda m: self.locked[int(m.group(1)) - 1] if int(m.group(1)) <= len(self.locked) else "", masked)

    @property
    def words(self) -> int:
        return len(self.text.split())


class DocumentModel(BaseModel):
    format: Literal["DOCX", "PDF"]
    blocks: list[Block]
    warnings: list[str] = []
    page_count: int | None = None

    @property
    def word_count(self) -> int:
        return sum(b.words for b in self.blocks)

    @property
    def heading_count(self) -> int:
        return sum(1 for b in self.blocks if b.kind == "heading")

    def outline(self) -> list[str]:
        return [("  " * ((b.level or 1) - 1)) + b.text for b in self.blocks if b.kind in ("title", "heading")]

    def by_id(self) -> dict[str, Block]:
        return {b.id: b for b in self.blocks}

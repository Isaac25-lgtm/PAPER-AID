"""Paragraph groups for Deep Redraft.

A group is a run of consecutive ordinary body paragraphs in one section, split into chunks of at
most MAX_GROUP_WORDS. Lists, tables, captions, quotations and headings end a group and are never
touched, nor is a paragraph that carries a Word section break or tracked changes.

Inside a group the writer may reorder, merge and split paragraphs, so locked items must be
identifiable across the whole group: each paragraph's ⟦Xn⟧ (Word fields, links, footnote
references, specially formatted runs) and ⟦Pn⟧ (citations, quotations, URLs found in the text)
tokens are renumbered group-wide. `protect.check_rewrite` then checks the joined group exactly as
it checks one paragraph: every locked item once, every number unchanged, no notes."""

from dataclasses import dataclass, field

from app.ai.orchestration import SEPARATOR
from app.analysis import signals
from app.documents import protect
from app.documents.model import Block, DocumentModel

MAX_GROUP_WORDS = 900
MIN_GROUP_WORDS = 25  # as for the analysis: a short, generic conclusion is often what most needs the work


@dataclass
class Group:
    id: str
    section: str
    block_ids: list[str]
    masked: str  # the group's paragraphs joined by SEPARATOR, with group-wide tokens
    xmap: dict[str, tuple[str, str]] = field(default_factory=dict)  # group Xg → (block id, paragraph Xn)
    pmap: dict[str, str] = field(default_factory=dict)  # group Pg → original text
    locked: dict[str, str] = field(default_factory=dict)  # group Xg → what the reader sees

    @property
    def words(self) -> int:
        return len(signals.TOKENS.sub(" ", self.masked).split())

    def readable(self, text: str) -> str:
        """Masked group text as the reader sees it."""
        restored = protect.unmask(text, self.pmap)
        return protect.TOKEN.sub(lambda m: self.locked.get(m.group(1), ""), restored)

    def paragraphs(self, text: str) -> list[str]:
        return [p.strip() for p in text.split(SEPARATOR) if p.strip()]


def _groupable(block: Block) -> bool:
    return block.kind == "paragraph" and block.editable and block.masked is not None and not block.section_break


def _build(n: int, section: str, blocks: list[Block]) -> Group:
    group = Group(id=f"g{n:03d}", section=section, block_ids=[b.id for b in blocks], masked="")
    parts = []
    xn = pn = 0
    for block in blocks:
        masked, originals = protect.mask(block.masked or "")
        local_p = {}
        for key, text in originals.items():
            pn += 1
            local_p[key] = f"P{pn}"
            group.pmap[f"P{pn}"] = text
        local_x = {}
        for i, _ in enumerate(block.locked, start=1):
            xn += 1
            local_x[f"X{i}"] = f"X{xn}"
            group.xmap[f"X{xn}"] = (block.id, f"X{i}")
            group.locked[f"X{xn}"] = block.locked[i - 1]
        names = {**local_x, **local_p}
        renamed = protect.TOKEN.sub(lambda m, names=names: f"⟦{names.get(m.group(1), m.group(1))}⟧", masked)
        parts.append(renamed.replace(SEPARATOR, " "))
    group.masked = SEPARATOR.join(parts)
    return group


def groups(model: DocumentModel) -> list[Group]:
    """Every redraftable group, in reading order. Deterministic: the same paper gives the same groups."""
    found: list[Group] = []
    run: list[Block] = []

    def close() -> None:
        chunk: list[Block] = []
        for block in run:
            if chunk and sum(b.words for b in chunk) + block.words > MAX_GROUP_WORDS:
                found.append(_build(len(found) + 1, chunk[0].section, chunk))
                chunk = []
            chunk.append(block)
        if chunk:
            found.append(_build(len(found) + 1, chunk[0].section, chunk))
        run.clear()

    barriers = sorted(int(b[1:]) for b in model.barriers)

    def divided(a: Block, b: Block) -> bool:
        low, high = int(a.id[1:]), int(b.id[1:])
        return any(low < x < high for x in barriers)

    for block in model.blocks:
        if _groupable(block) and (not run or (run[-1].section == block.section and not divided(run[-1], block))):
            run.append(block)
            continue
        close()
        if _groupable(block):
            run.append(block)
    close()
    return [g for g in found if g.words >= MIN_GROUP_WORDS]


def to_docx(group: Group, revised: str) -> list[str]:
    """The group's new paragraphs for the Word file: citations and quotations restored as text,
    Word-level items left as group-wide ⟦Xg⟧ tokens for `apply_group_rewrites` to put back."""
    return [protect.unmask(p, group.pmap) for p in group.paragraphs(revised)]


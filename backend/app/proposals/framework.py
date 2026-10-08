"""The conceptual framework as a figure (owner request 2026-10-01; reworked 2026-10-08 with Codex's
recommendations): the approved plan's independent variables in boxes on the left, the outcome on the
right, intervening variables distinguished below, and arrows that mean "association examined", never
proven causation. A qualitative study gets a concept framework instead: the phenomenon at the centre and
the areas the study explores around it. Black and white by default, muted green or blue on request (a
style change only redraws it). Every variable is drawn: the layout adapts, nothing is left out. One PNG
serves the Word file, the PDF, the app and its own download, with a text description beside it for
readers who cannot see the image."""

import io
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from app.proposals.models import ProposalPlan, Variables

Style = Literal["MONO", "GREEN", "BLUE"]
STYLES: tuple[Style, ...] = ("MONO", "GREEN", "BLUE")


@dataclass(frozen=True)
class Palette:
    box: tuple[int, int, int]  # an independent variable's fill
    line: tuple[int, int, int]  # box borders
    outcome: tuple[int, int, int]  # the dependent variable's fill
    outcome_ink: tuple[int, int, int]
    ink: tuple[int, int, int]
    arrow: tuple[int, int, int]
    label: tuple[int, int, int]
    muted: tuple[int, int, int]  # intervening variables and the legend


BLACK, WHITE = (0, 0, 0), (255, 255, 255)
PALETTES: dict[Style, Palette] = {
    # white boxes, dark borders and arrows: prints and photocopies cleanly (the default)
    "MONO": Palette(box=WHITE, line=BLACK, outcome=WHITE, outcome_ink=BLACK, ink=BLACK, arrow=BLACK, label=BLACK, muted=(64, 64, 64)),
    "GREEN": Palette(box=(240, 247, 242), line=(46, 94, 62), outcome=(214, 234, 220), outcome_ink=(20, 50, 30), ink=(17, 24, 39),
                     arrow=(46, 94, 62), label=(30, 70, 45), muted=(90, 100, 95)),
    "BLUE": Palette(box=(240, 245, 251), line=(44, 77, 120), outcome=(214, 227, 243), outcome_ink=(18, 38, 66), ink=(17, 24, 39),
                    arrow=(44, 77, 120), label=(30, 58, 95), muted=(90, 96, 108)),
}
WIDTH, MARGIN, GAP = 2000, 40, 26
COLUMN = 760  # each side column; the arrows cross the space between
FONTS = ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf")
BOLD_FONTS = ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf")
SOURCE = "Source: Researcher's own conceptualisation."


@lru_cache(maxsize=16)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in BOLD_FONTS if bold else FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue  # not installed here: the next candidate, then Pillow's own scalable font
    return ImageFont.load_default(size=size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words, line = paragraph.split(), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.getlength(candidate) <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines or [""]


def _split(item: str) -> tuple[str, str]:
    """"Caregiver factors: age, education" → a bold group name and its detail."""
    head, sep, rest = item.partition(":")
    return (head.strip(), rest.strip()) if sep and 2 <= len(head.strip()) <= 60 and rest.strip() else ("", item.strip())


class _Box:
    def __init__(self, item: str, width: int, size: int) -> None:
        self.head, self.body = _split(item)
        self.width, self.pad = width, max(14, size * 3 // 4)
        self.head_font, self.body_font = _font(size, bold=True), _font(size)
        self.head_lines = _wrap(self.head, self.head_font, width - 2 * self.pad) if self.head else []
        self.body_lines = _wrap(self.body, self.body_font, width - 2 * self.pad) if self.body else []
        self.line = int(size * 1.35)
        self.height = 2 * self.pad + self.line * (len(self.head_lines) + len(self.body_lines))

    def draw(self, d: ImageDraw.ImageDraw, x: int, y: int, fill: tuple[int, int, int], outline: tuple[int, int, int], ink: tuple[int, int, int],
             dashed: bool = False, border: int = 4) -> None:
        if dashed:
            d.rectangle((x, y, x + self.width, y + self.height), fill=fill)
            _dashed_rect(d, x, y, x + self.width, y + self.height, outline)
        else:
            d.rectangle((x, y, x + self.width, y + self.height), fill=fill, outline=outline, width=border)
        ty = y + self.pad
        for text in self.head_lines:
            d.text((x + self.pad, ty), text, font=self.head_font, fill=ink)
            ty += self.line
        for text in self.body_lines:
            d.text((x + self.pad, ty), text, font=self.body_font, fill=ink)
            ty += self.line


def _dashed_rect(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, colour: tuple[int, int, int], dash: int = 18) -> None:
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        length = max(abs(bx - ax), abs(by - ay))
        for start in range(0, length, dash * 2):
            t0, t1 = start / length, min(start + dash, length) / length
            d.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1), fill=colour, width=4)


def _arrow(d: ImageDraw.ImageDraw, x0: float, y0: float, x1: float, y1: float, colour: tuple[int, int, int], width: int = 5, dashed: bool = False,
           head: bool = True) -> None:
    angle = math.atan2(y1 - y0, x1 - x0)
    size = 26
    end_x, end_y = (x1 - size * 0.8 * math.cos(angle), y1 - size * 0.8 * math.sin(angle)) if head else (x1, y1)
    if dashed:
        length = math.hypot(end_x - x0, end_y - y0)
        steps = max(1, int(length // 30))
        for i in range(0, steps, 2):
            a, b = i / steps, min(i + 1, steps) / steps
            d.line((x0 + (end_x - x0) * a, y0 + (end_y - y0) * a, x0 + (end_x - x0) * b, y0 + (end_y - y0) * b), fill=colour, width=width)
    else:
        d.line((x0, y0, end_x, end_y), fill=colour, width=width)
    if head:
        left = (x1 - size * math.cos(angle - 0.42), y1 - size * math.sin(angle - 0.42))
        right = (x1 - size * math.cos(angle + 0.42), y1 - size * math.sin(angle + 0.42))
        d.polygon([(x1, y1), left, right], fill=colour)


def _label(item: str) -> str:
    """A box shows the variable, not its whole operational definition ("...uptake, defined using the
    national schedule; history checked against the card..."): the first clause; the alternative text
    keeps every word."""
    text = item.split(";")[0].strip()
    for marker in (", defined ", " defined as ", ", measured "):
        if marker in text:
            text = text.split(marker)[0].strip()
    return text.rstrip(",.") or item.strip()


def _size(count: int) -> int:
    """Smaller text as boxes are added, so every variable fits: none is ever left out (Codex 2026-10-08)."""
    return 30 if count <= 5 else 26 if count <= 8 else 22 if count <= 12 else 19


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def draw(variables: Variables, style: Style = "MONO") -> bytes | None:
    """The framework as a PNG, or None when the study has no independent and dependent variables."""
    palette = PALETTES.get(style, PALETTES["MONO"])
    independent = [_label(v) for v in variables.independent if v.strip()]
    dependent = [_label(v) for v in variables.dependent if v.strip()]
    intervening = [_label(v) for v in variables.intervening if v.strip()]
    if not independent or not dependent:
        return None
    size = _size(len(independent))
    label_font = _font(32, bold=True)
    left = [_Box(v, COLUMN, size) for v in independent]
    right = [_Box(v, COLUMN, _size(len(dependent)) + 2) for v in dependent]
    middle = None
    if intervening:
        text = "; ".join(intervening)
        widest = WIDTH - 2 * MARGIN - 2 * 160
        middle = _Box(text, min(widest, int(_font(size).getlength(text)) + 2 * 22 + 8), size)
    top = MARGIN + 60  # under the column labels
    left_height = sum(b.height for b in left) + GAP * (len(left) - 1)
    right_height = sum(b.height for b in right) + GAP * (len(right) - 1)
    body = max(left_height, right_height)
    height = top + body + (80 + 50 + middle.height if middle else 0) + 90 + MARGIN
    image = Image.new("RGB", (WIDTH, height), "white")
    d = ImageDraw.Draw(image)
    rx = WIDTH - MARGIN - COLUMN
    d.text((MARGIN, MARGIN), "Independent variables" if len(left) > 1 else "Independent variable", font=label_font, fill=palette.label)
    d.text((rx, MARGIN), "Dependent variables" if len(right) > 1 else "Dependent variable", font=label_font, fill=palette.label)

    y = top + (body - left_height) // 2
    anchors = []
    for box in left:
        box.draw(d, MARGIN, y, palette.box, palette.line, palette.ink)
        anchors.append(y + box.height / 2)
        y += box.height + GAP
    y = top + (body - right_height) // 2
    targets = []
    for box in right:
        box.draw(d, rx, y, palette.outcome, palette.line, palette.outcome_ink, border=6)  # the outcome: a heavier border
        targets.append((y, y + box.height))
        y += box.height + GAP
    first, last = targets[0][0], targets[-1][1]
    for n, ay in enumerate(anchors):
        share = (n + 1) / (len(anchors) + 1)
        ty = first + (last - first) * share
        _arrow(d, MARGIN + COLUMN + 8, ay, rx - 10, ty, palette.arrow, width=4 if len(anchors) > 8 else 5)
    bottom = top + body
    if middle is not None:
        mx = (WIDTH - middle.width) // 2
        my = bottom + 80 + 50
        d.text((mx, bottom + 80), "Intervening variables" if len(intervening) > 1 else "Intervening variable", font=label_font, fill=palette.muted)
        middle.draw(d, mx, my, WHITE, palette.muted, palette.ink, dashed=True)
        cx = WIDTH / 2
        _arrow(d, cx, bottom + 66, cx, (first + last) / 2 + 14, palette.muted, width=4, dashed=True)  # from above its label onto the associations
        bottom = my + middle.height
    note_font = _font(24)
    legend_y = bottom + 40
    _arrow(d, MARGIN, legend_y + 14, MARGIN + 90, legend_y + 14, palette.arrow, width=4)
    d.text((MARGIN + 110, legend_y), "association this study will examine (not proven cause)", font=note_font, fill=palette.muted)
    if middle is not None:
        _arrow(d, WIDTH // 2 + 60, legend_y + 14, WIDTH // 2 + 150, legend_y + 14, palette.muted, width=4, dashed=True)
        d.text((WIDTH // 2 + 170, legend_y), "may affect the association", font=note_font, fill=palette.muted)
    return _png(image)


# "To explore the experiences of ..." → "Experiences of ...": the area an objective explores.
_VERB = re.compile(r"^\s*to\s+(?:explore|examine|assess|describe|determine|identify|establish|investigate|understand|analyse|analyze|"
                   r"document|evaluate|find out|map|compare|ascertain)\s+(?:the\s+)?", re.I)


def concepts(plan: ProposalPlan) -> tuple[str, list[str]]:
    """A qualitative study's framework: its phenomenon and the areas its objectives explore."""
    areas = []
    for objective in plan.specific_objectives:
        text = _VERB.sub("", objective.strip()).rstrip(".")
        if text:
            areas.append(text[0].upper() + text[1:])
    centre = _VERB.sub("", plan.purpose.strip()).rstrip(".") or plan.title.strip()
    return (centre[0].upper() + centre[1:] if centre else ""), areas


def draw_concepts(plan: ProposalPlan, style: Style = "MONO") -> bytes | None:
    """A concept framework for a qualitative study (Codex 2026-10-08: never independent and dependent
    variables forced on it): the phenomenon at the centre, the areas the study explores below it, joined
    by plain lines (no arrows: nothing is claimed about cause or direction)."""
    palette = PALETTES.get(style, PALETTES["MONO"])
    centre, areas = concepts(plan)
    if not centre or not areas:
        return None
    per_row = len(areas) if len(areas) <= 5 else math.ceil(len(areas) / 2)
    cell = (WIDTH - 2 * MARGIN - GAP * (per_row - 1)) // per_row
    size = 30 if per_row <= 3 else 24 if per_row == 4 else 21
    top_box = _Box(f"Phenomenon: {centre}", min(WIDTH - 2 * MARGIN, 1200), 30)
    boxes = [_Box(a, cell, size) for a in areas]
    rows = [boxes[i:i + per_row] for i in range(0, len(boxes), per_row)]
    row_heights = [max(b.height for b in row) for row in rows]
    top, drop = MARGIN + 60, 70  # each row hangs from its own line, `drop` above it
    first_row = top + top_box.height + 40 + drop
    height = first_row + sum(row_heights) + (GAP + drop) * (len(rows) - 1) + 90 + MARGIN
    image = Image.new("RGB", (WIDTH, height), "white")
    d = ImageDraw.Draw(image)
    d.text((MARGIN, MARGIN), "Concept framework", font=_font(32, bold=True), fill=palette.label)
    top_box.draw(d, (WIDTH - top_box.width) // 2, top, palette.outcome, palette.line, palette.outcome_ink, border=6)
    trunk = MARGIN // 2  # rows after the first join the phenomenon along the left edge
    hub = first_row - drop // 2
    d.line((WIDTH / 2, top + top_box.height, WIDTH / 2, hub), fill=palette.arrow, width=4)
    y = first_row
    for i, (row, row_height) in enumerate(zip(rows, row_heights, strict=True)):
        width = len(row) * cell + GAP * (len(row) - 1)
        x = (WIDTH - width) // 2
        line_y = y - drop // 2
        xs = [x + j * (cell + GAP) + cell / 2 for j in range(len(row))]
        d.line((min(xs + [WIDTH / 2] if i == 0 else xs + [trunk]), line_y, max(xs + [WIDTH / 2] if i == 0 else xs), line_y), fill=palette.arrow, width=4)
        if i:
            d.line((trunk, hub, trunk, line_y), fill=palette.arrow, width=4)
        for box, cx in zip(row, xs, strict=True):
            d.line((cx, line_y, cx, y), fill=palette.arrow, width=4)
            box.draw(d, x, y, palette.box, palette.line, palette.ink)
            x += cell + GAP
        y += row_height + GAP + drop
    y -= drop
    if len(rows) > 1:
        d.line((trunk, hub, WIDTH / 2, hub), fill=palette.arrow, width=4)
    note_font = _font(24)
    d.text((MARGIN, y + 20), "Lines join the phenomenon to the areas the study will explore; they claim no cause or direction.", font=note_font, fill=palette.muted)
    return _png(image)


def figure(plan: ProposalPlan | None, style: Style = "MONO") -> bytes | None:
    """The study's framework figure: variables when it has them, else a concept framework for a
    qualitative study; None when neither applies (a desk review, for example)."""
    if plan is None:
        return None
    png = draw(plan.variables, style)
    if png is None and plan.study_type == "QUALITATIVE":
        png = draw_concepts(plan, style)
    return png


def note(plan: ProposalPlan | None) -> str:
    """The note printed under the figure, the same in the app, the Word file and the PDF."""
    if plan is not None and draw_kind(plan) == "CONCEPTS":
        return f"Lines join the phenomenon to the areas the study will explore; they claim no cause or direction. {SOURCE}"
    return f"Arrows show the associations this study will examine; they do not imply proven causes. {SOURCE}"


def draw_kind(plan: ProposalPlan) -> Literal["VARIABLES", "CONCEPTS", "NONE"]:
    v = plan.variables
    if any(x.strip() for x in v.independent) and any(x.strip() for x in v.dependent):
        return "VARIABLES"
    if plan.study_type == "QUALITATIVE" and all(concepts(plan)):
        return "CONCEPTS"
    return "NONE"


def describe(variables: Variables) -> str:
    """The same figure in words: its alternative text and the app's description."""
    independent = [v.strip() for v in variables.independent if v.strip()]
    dependent = [v.strip() for v in variables.dependent if v.strip()]
    intervening = [v.strip() for v in variables.intervening if v.strip()]
    if not independent or not dependent:
        return ""
    text = f"The study will examine the association between {_series([_phrase(v) for v in independent])} (independent) and {_series([_phrase(v) for v in dependent])} (dependent)."
    if intervening:
        text += f" {_series([_phrase(v) for v in intervening], upper=True)} {'are' if len(intervening) > 1 else 'is'} considered as intervening."
    return text


def describe_plan(plan: ProposalPlan | None) -> str:
    """The figure in words, whichever kind it is."""
    if plan is None:
        return ""
    kind = draw_kind(plan)
    if kind == "VARIABLES":
        return describe(plan.variables)
    if kind == "CONCEPTS":
        centre, areas = concepts(plan)
        return f"The study explores {centre[0].lower() + centre[1:]} through {_series([a[0].lower() + a[1:] for a in areas])}."
    return ""


def _phrase(item: str) -> str:
    """"Caregiver factors: age, education" → "caregiver factors (age, education)"."""
    head, body = _split(item)
    return f"{head[0].lower() + head[1:]} ({body})" if head else body[0].lower() + body[1:] if body[:2] != body[:2].upper() else body


def _series(items: list[str], upper: bool = False) -> str:
    items = [i.rstrip(".") for i in items]
    text = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return text[0].upper() + text[1:] if upper and text else text

"""The conceptual framework as a figure (owner request 2026-10-01): the approved plan's independent
variables in boxes on the left, the outcome on the right, intervening variables distinguished below,
and arrows that mean "association examined", never proven causation. One PNG serves the Word file,
the PDF and the app, with a text description beside it for readers who cannot see the image."""

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.proposals.models import Variables

# PaperAid green, with neutral greys (one palette for the app and the document).
GREEN, GREEN_DARK, GREEN_TINT = (21, 128, 61), (20, 83, 45), (240, 253, 244)
INK, MUTED, LINE, GREY_TINT = (17, 24, 39), (75, 85, 99), (156, 163, 175), (249, 250, 251)
WIDTH, MARGIN, GAP = 2000, 40, 26
COLUMN = 760  # each side column; the arrows cross the space between
FONTS = ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf")
BOLD_FONTS = ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf")


@lru_cache(maxsize=8)
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
        self.width, self.pad = width, 22
        self.head_font, self.body_font = _font(size, bold=True), _font(size)
        self.head_lines = _wrap(self.head, self.head_font, width - 2 * self.pad) if self.head else []
        self.body_lines = _wrap(self.body, self.body_font, width - 2 * self.pad) if self.body else []
        self.line = int(size * 1.35)
        self.height = 2 * self.pad + self.line * (len(self.head_lines) + len(self.body_lines))

    def draw(self, d: ImageDraw.ImageDraw, x: int, y: int, fill: tuple[int, int, int], outline: tuple[int, int, int], ink: tuple[int, int, int], dashed: bool = False) -> None:
        if dashed:
            d.rounded_rectangle((x, y, x + self.width, y + self.height), radius=16, fill=fill)
            _dashed_rect(d, x, y, x + self.width, y + self.height, outline)
        else:
            d.rounded_rectangle((x, y, x + self.width, y + self.height), radius=16, fill=fill, outline=outline, width=4)
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


def _arrow(d: ImageDraw.ImageDraw, x0: float, y0: float, x1: float, y1: float, colour: tuple[int, int, int], width: int = 5, dashed: bool = False) -> None:
    import math

    angle = math.atan2(y1 - y0, x1 - x0)
    head = 26
    end_x, end_y = x1 - head * 0.8 * math.cos(angle), y1 - head * 0.8 * math.sin(angle)
    if dashed:
        length = math.hypot(end_x - x0, end_y - y0)
        steps = int(length // 30)
        for i in range(0, steps, 2):
            a, b = i / steps, min(i + 1, steps) / steps
            d.line((x0 + (end_x - x0) * a, y0 + (end_y - y0) * a, x0 + (end_x - x0) * b, y0 + (end_y - y0) * b), fill=colour, width=width)
    else:
        d.line((x0, y0, end_x, end_y), fill=colour, width=width)
    left = (x1 - head * math.cos(angle - 0.42), y1 - head * math.sin(angle - 0.42))
    right = (x1 - head * math.cos(angle + 0.42), y1 - head * math.sin(angle + 0.42))
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


def draw(variables: Variables) -> bytes | None:
    """The framework as a PNG, or None when the study has no independent and dependent variables
    (a qualitative design gets no variable diagram)."""
    independent = [_label(v) for v in variables.independent if v.strip()][:10]
    dependent = [_label(v) for v in variables.dependent if v.strip()][:3]
    intervening = [_label(v) for v in variables.intervening if v.strip()][:6]
    if not independent or not dependent:
        return None
    size = 30 if len(independent) <= 5 else 26
    label_font = _font(32, bold=True)
    left = [_Box(v, COLUMN, size) for v in independent]
    right = [_Box(v, COLUMN, size + 2) for v in dependent]
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
    d.text((MARGIN, MARGIN), "Independent variables" if len(left) > 1 else "Independent variable", font=label_font, fill=GREEN_DARK)
    d.text((rx, MARGIN), "Dependent variables" if len(right) > 1 else "Dependent variable", font=label_font, fill=GREEN_DARK)

    y = top + (body - left_height) // 2
    anchors = []
    for box in left:
        box.draw(d, MARGIN, y, GREEN_TINT, GREEN, INK)
        anchors.append(y + box.height / 2)
        y += box.height + GAP
    y = top + (body - right_height) // 2
    targets = []
    for box in right:
        box.draw(d, rx, y, GREEN, GREEN_DARK, (255, 255, 255))
        targets.append((y, y + box.height))
        y += box.height + GAP
    first, last = targets[0][0], targets[-1][1]
    for n, ay in enumerate(anchors):
        share = (n + 1) / (len(anchors) + 1)
        ty = first + (last - first) * share
        _arrow(d, MARGIN + COLUMN + 8, ay, rx - 10, ty, MUTED)
    bottom = top + body
    if middle is not None:
        mx = (WIDTH - middle.width) // 2
        my = bottom + 80 + 50
        d.text((mx, bottom + 80), "Intervening variables" if len(intervening) > 1 else "Intervening variable", font=label_font, fill=MUTED)
        middle.draw(d, mx, my, GREY_TINT, LINE, INK, dashed=True)
        cx = WIDTH / 2
        _arrow(d, cx, my - 6, cx, (first + last) / 2 + 14, LINE, width=4, dashed=True)  # onto the associations it may affect
        bottom = my + middle.height
    note_font = _font(24)
    legend_y = bottom + 40
    _arrow(d, MARGIN, legend_y + 14, MARGIN + 90, legend_y + 14, MUTED, width=4)
    d.text((MARGIN + 110, legend_y), "association this study will examine (not proven cause)", font=note_font, fill=MUTED)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


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


def _phrase(item: str) -> str:
    """"Caregiver factors: age, education" → "caregiver factors (age, education)"."""
    head, body = _split(item)
    return f"{head[0].lower() + head[1:]} ({body})" if head else body[0].lower() + body[1:] if body[:2] != body[:2].upper() else body


def _series(items: list[str], upper: bool = False) -> str:
    items = [i.rstrip(".") for i in items]
    text = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return text[0].upper() + text[1:] if upper and text else text

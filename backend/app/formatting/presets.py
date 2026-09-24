"""FormattingSpec: the typed rules the deterministic formatter consumes. Curated presets and
(later) parsed university guidelines both produce this same structure."""

from typing import Literal

from pydantic import BaseModel


class HeadingStyle(BaseModel):
    size_pt: float
    bold: bool = True
    italic: bool = False
    align: Literal["left", "center"] = "left"


class FormattingSpec(BaseModel):
    id: str
    label: str
    margins_cm: tuple[float, float, float, float]  # top, bottom, left, right
    font: str
    size_pt: float
    line_spacing: float
    first_line_indent_cm: float
    space_after_pt: float
    alignment: Literal["left", "justify"]
    headings: dict[int, HeadingStyle]
    heading_space_before_pt: float
    heading_space_after_pt: float
    page_numbers: Literal["top-right", "top-center", "bottom-center", "bottom-right"]
    roman_preliminary_pages: bool
    references_hanging_cm: float
    references_line_spacing: float
    insert_toc: bool
    paper_size: Literal["A4", "Letter"] = "A4"


PRESETS: dict[str, FormattingSpec] = {
    "apa7": FormattingSpec(
        id="apa7",
        label="APA 7th edition (student paper)",
        margins_cm=(2.54, 2.54, 2.54, 2.54),
        font="Times New Roman",
        size_pt=12,
        line_spacing=2.0,
        first_line_indent_cm=1.27,
        space_after_pt=0,
        alignment="left",
        headings={
            1: HeadingStyle(size_pt=12, bold=True, align="center"),
            2: HeadingStyle(size_pt=12, bold=True),
            3: HeadingStyle(size_pt=12, bold=True, italic=True),
        },
        heading_space_before_pt=0,
        heading_space_after_pt=0,
        page_numbers="top-right",
        roman_preliminary_pages=False,
        references_hanging_cm=1.27,
        references_line_spacing=2.0,
        insert_toc=False,
    ),
    "harvard": FormattingSpec(
        id="harvard",
        label="Harvard (general, report/dissertation layout)",
        margins_cm=(2.5, 2.5, 3.0, 2.5),
        font="Times New Roman",
        size_pt=12,
        line_spacing=1.5,
        first_line_indent_cm=0,
        space_after_pt=6,
        alignment="justify",
        headings={
            1: HeadingStyle(size_pt=14, bold=True, align="center"),
            2: HeadingStyle(size_pt=12, bold=True),
            3: HeadingStyle(size_pt=12, bold=True, italic=True),
        },
        heading_space_before_pt=12,
        heading_space_after_pt=6,
        page_numbers="bottom-center",
        roman_preliminary_pages=True,
        references_hanging_cm=1.27,
        references_line_spacing=1.0,
        insert_toc=True,
    ),
}

PUBLIC_PRESETS = [
    {"id": "apa7", "label": "APA 7th edition", "available": True},
    {"id": "harvard", "label": "Harvard (general)", "available": True},
    {"id": "university", "label": "University presets — coming soon", "available": False},
]

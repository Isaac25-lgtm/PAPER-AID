"""FormattingSpec: the typed rules the deterministic formatter consumes. Curated presets and
(later) parsed university guidelines both produce this same structure."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


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
    # Non-academic documents (master context §81): clean layouts without academic headings rules.
    "professional": FormattingSpec(
        id="professional",
        label="Professional (clean document)",
        margins_cm=(2.54, 2.54, 2.54, 2.54),
        font="Calibri",
        size_pt=11,
        line_spacing=1.15,
        first_line_indent_cm=0,
        space_after_pt=8,
        alignment="left",
        headings={
            1: HeadingStyle(size_pt=16, bold=True),
            2: HeadingStyle(size_pt=13, bold=True),
            3: HeadingStyle(size_pt=11, bold=True),
        },
        heading_space_before_pt=12,
        heading_space_after_pt=4,
        page_numbers="bottom-right",
        roman_preliminary_pages=False,
        references_hanging_cm=0.63,
        references_line_spacing=1.0,
        insert_toc=False,
    ),
    "report": FormattingSpec(
        id="report",
        label="Report (with contents page)",
        margins_cm=(2.5, 2.5, 2.5, 2.5),
        font="Arial",
        size_pt=11,
        line_spacing=1.15,
        first_line_indent_cm=0,
        space_after_pt=6,
        alignment="justify",
        headings={
            1: HeadingStyle(size_pt=15, bold=True),
            2: HeadingStyle(size_pt=12.5, bold=True),
            3: HeadingStyle(size_pt=11, bold=True, italic=True),
        },
        heading_space_before_pt=12,
        heading_space_after_pt=6,
        page_numbers="bottom-center",
        roman_preliminary_pages=True,
        references_hanging_cm=0.63,
        references_line_spacing=1.0,
        insert_toc=True,
    ),
}

PUBLIC_PRESETS = [
    {"id": "apa7", "label": "APA 7th edition", "available": True},
    {"id": "harvard", "label": "Harvard (general)", "available": True},
    {"id": "professional", "label": "Professional (non-academic)", "available": True},
    {"id": "report", "label": "Report (non-academic)", "available": True},
]

FONTS = ["Times New Roman", "Calibri", "Arial", "Trebuchet MS", "Georgia", "Cambria", "Garamond", "Book Antiqua"]


class CustomLayout(BaseModel):
    """The student's own choices over a preset (master context §16). Unset fields keep the preset's."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    font: Literal["Times New Roman", "Calibri", "Arial", "Trebuchet MS", "Georgia", "Cambria", "Garamond", "Book Antiqua"] | None = None
    size_pt: float | None = Field(default=None, ge=10, le=14)
    line_spacing: Literal[1.0, 1.15, 1.5, 2.0] | None = None
    margin_cm: float | None = Field(default=None, ge=1.5, le=4.0)  # all four sides
    alignment: Literal["left", "justify"] | None = None


def with_custom(spec: FormattingSpec, custom: CustomLayout | None) -> FormattingSpec:
    if custom is None:
        return spec
    update: dict = {}
    if custom.font:
        update["font"] = custom.font
    if custom.size_pt:
        update["size_pt"] = custom.size_pt
        update["headings"] = {level: h.model_copy(update={"size_pt": max(h.size_pt, custom.size_pt)}) for level, h in spec.headings.items()}
    if custom.line_spacing:
        update["line_spacing"] = custom.line_spacing
    if custom.margin_cm:
        update["margins_cm"] = (custom.margin_cm,) * 4
    if custom.alignment:
        update["alignment"] = custom.alignment
    if not update:
        return spec
    return spec.model_copy(update={**update, "id": f"{spec.id}-custom", "label": f"{spec.label}, with your settings"})

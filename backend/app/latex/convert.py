"""DOCX → LaTeX conversion (owner decision 2026-09-27: deterministic code, no AI, fixed price).

The converter walks the Word body in order and writes a plain `article` document:
headings → \\section…, runs keep bold/italic/underline/super- and subscript, links → \\href,
footnotes → \\footnote, Word lists → itemize/enumerate, tables → wrapping columns (merged cells
as \\multicolumn), images → figures/ files, Word equations → LaTeX maths for the common
structures. Citations stay exactly as displayed and the reference list exactly as written.

Nothing is guessed: an equation, image or element the converter cannot express faithfully is
left out of the output with a LaTeX comment where it was, and listed in the warnings. All text is
escaped, so the student's words can never become LaTeX commands.
"""

import io
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from docx import Document
from docx.text.paragraph import Paragraph

from app.documents.docx_io import detect_fake_heading

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

SECTIONS = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}
REFERENCES = re.compile(r"^(references|reference list|bibliography|works cited|literature cited)$", re.I)
MANUAL_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.)\s+")
IMAGE_TYPES = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "pdf": "pdf"}

PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage[margin=2.54cm]{geometry}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{array}
\usepackage[hidelinks]{hyperref}
\setlength{\parskip}{0.6em}
\setlength{\parindent}{0pt}
"""

# Text characters: LaTeX specials, typography and common symbols outside T1.
TEXT_MAP = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}",
    "“": "``", "”": "''", "‘": "`", "’": "'", "–": "--", "—": "---", "…": r"\ldots{}", "\u00a0": "~", "\u200b": "",
    "°": r"\textdegree{}", "×": r"\texttimes{}", "÷": r"\textdiv{}", "±": r"\textpm{}", "€": r"\texteuro{}", "™": r"\texttrademark{}",
    "≤": r"$\leq$", "≥": r"$\geq$", "≠": r"$\neq$", "≈": r"$\approx$", "→": r"$\rightarrow$", "←": r"$\leftarrow$", "∞": r"$\infty$",
    "µ": r"$\mu$", "•": r"\textbullet{}", "√": r"$\surd$",
    "■": r"\rule{1.2ex}{1.2ex}", "▪": r"\rule{0.9ex}{0.9ex}",  # a funding workplan's active months (app.works.results.workplan)
}
GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
    "ψ": "psi", "ω": "omega", "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma", "Φ": "Phi",
    "Ψ": "Psi", "Ω": "Omega",
}
# Symbols inside Word equations.
MATH_MAP = {
    **{k: "\\" + v + " " for k, v in GREEK.items()},
    "≤": r"\leq ", "≥": r"\geq ", "≠": r"\neq ", "≈": r"\approx ", "±": r"\pm ", "∓": r"\mp ", "×": r"\times ", "÷": r"\div ", "·": r"\cdot ",
    "∞": r"\infty ", "→": r"\to ", "←": r"\leftarrow ", "⇒": r"\Rightarrow ", "∈": r"\in ", "∉": r"\notin ", "⊂": r"\subset ", "∪": r"\cup ",
    "∩": r"\cap ", "∂": r"\partial ", "∇": r"\nabla ", "−": "-", "′": "'", "…": r"\ldots ", "⋯": r"\cdots ", "∑": r"\sum ", "∏": r"\prod ", "∫": r"\int ",
    "%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "$": r"\$", "\\": r"\backslash ",
}
NARY = {"∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint", "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap"}
ACCENTS = {"\u0302": r"\hat", "\u0303": r"\tilde", "\u0304": r"\bar", "\u0307": r"\dot", "\u0308": r"\ddot", "\u20d7": r"\vec"}


class Unsupported(Exception):
    """An element the converter cannot express faithfully."""


@dataclass
class Result:
    tex: str
    files: dict[str, bytes] = field(default_factory=dict)  # published path → bytes (figures)
    warnings: list[str] = field(default_factory=list)
    equations: int = 0
    equations_converted: int = 0
    figures: int = 0
    omitted: int = 0  # items left out of main.tex (each has a warning): the result is partial


LINK_SCHEMES = ("http", "https", "mailto")
# Characters a URL may keep inside \href: everything else (braces, backslashes, spaces, ^, ~, |…)
# is percent-encoded, so a link target can never close the argument or start a TeX command.
URL_SAFE = "/:?&=@+,;!*'()-._%#"


def safe_url(url: str) -> str | None:
    r"""A link target that is safe inside \href{…}, or None when it should stay plain text."""
    target = url.strip()
    if urlsplit(target).scheme.lower() not in LINK_SCHEMES:
        return None
    encoded = quote(target, safe=URL_SAFE)
    return encoded.replace("%", r"\%").replace("#", r"\#")


def escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in TEXT_MAP:
            out.append(TEXT_MAP[ch])
        elif ch in GREEK:
            out.append(f"$\\{GREEK[ch]}$")
        elif ord(ch) < 32 and ch not in "\t\n":
            continue
        else:
            out.append(ch)
    return "".join(out)


# --- Word equations (OMML) ------------------------------------------------------------------


def _children(el, tag: str):
    return el.find(M + tag)


def _omml(el) -> str:
    """LaTeX for an OMML element; raises Unsupported for anything not handled faithfully."""
    tag = el.tag.replace(M, "")
    if tag in ("oMath", "e", "num", "den", "sup", "sub", "deg", "fName", "lim"):
        return "".join(_omml(c) for c in el if c.tag.startswith(M) and not c.tag.endswith("Pr"))
    if tag == "r":
        text = "".join(t.text or "" for t in el.iter(M + "t"))
        return "".join(MATH_MAP.get(ch, ch) for ch in text)
    if tag == "f":
        return r"\frac{%s}{%s}" % (_omml(_children(el, "num")), _omml(_children(el, "den")))
    if tag == "sSup":
        return "{%s}^{%s}" % (_omml(_children(el, "e")), _omml(_children(el, "sup")))
    if tag == "sSub":
        return "{%s}_{%s}" % (_omml(_children(el, "e")), _omml(_children(el, "sub")))
    if tag == "sSubSup":
        return "{%s}_{%s}^{%s}" % (_omml(_children(el, "e")), _omml(_children(el, "sub")), _omml(_children(el, "sup")))
    if tag == "rad":
        deg = _children(el, "deg")
        degree = _omml(deg) if deg is not None else ""
        return (r"\sqrt[%s]{%s}" % (degree, _omml(_children(el, "e")))) if degree else r"\sqrt{%s}" % _omml(_children(el, "e"))
    if tag == "d":
        pr = _children(el, "dPr")
        beg = pr.find(M + "begChr") if pr is not None else None
        end = pr.find(M + "endChr") if pr is not None else None
        left = beg.get(M + "val") if beg is not None else "("
        right = end.get(M + "val") if end is not None else ")"
        fences = {"(": "(", ")": ")", "[": "[", "]": "]", "{": r"\{", "}": r"\}", "|": "|", "": "."}
        if left not in fences or right not in fences:
            raise Unsupported(f"delimiter {left}{right}")
        inner = ",".join(_omml(e) for e in el.findall(M + "e"))
        return r"\left%s %s \right%s" % (fences[left], inner, fences[right])
    if tag == "nary":
        pr = _children(el, "naryPr")
        chr_el = pr.find(M + "chr") if pr is not None else None
        symbol = chr_el.get(M + "val") if chr_el is not None else "∫"
        if symbol not in NARY:
            raise Unsupported(f"operator {symbol}")
        sub, sup = _children(el, "sub"), _children(el, "sup")
        limits = (f"_{{{_omml(sub)}}}" if sub is not None and len(sub) else "") + (f"^{{{_omml(sup)}}}" if sup is not None and len(sup) else "")
        return f"{NARY[symbol]}{limits} {{{_omml(_children(el, 'e'))}}}"
    if tag == "acc":
        pr = _children(el, "accPr")
        chr_el = pr.find(M + "chr") if pr is not None else None
        accent = ACCENTS.get(chr_el.get(M + "val") if chr_el is not None else "\u0302")
        if accent is None:
            raise Unsupported("accent")
        return f"{accent}{{{_omml(_children(el, 'e'))}}}"
    if tag == "bar":
        return r"\overline{%s}" % _omml(_children(el, "e"))
    if tag == "func":
        name = _omml(_children(el, "fName")).strip()
        known = {"sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim", "det"}
        head = f"\\{name}" if name in known else r"\operatorname{%s}" % name
        return f"{head} {_omml(_children(el, 'e'))}"
    if tag == "limLow":
        return r"%s_{%s}" % (_omml(_children(el, "e")), _omml(_children(el, "lim")))
    if tag in ("ctrlPr", "rPr"):
        return ""
    raise Unsupported(tag)


# --- the converter ----------------------------------------------------------------------------


class _Converter:
    def __init__(self, data: bytes):
        self.doc = Document(io.BytesIO(data))
        self.result = Result(tex="")
        self.out: list[str] = []
        self.title = ""
        self.lists: list[str] = []  # open list environments, innermost last
        self.footnotes = self._footnotes()
        self.numbering = self._numbering()
        self.in_references = False
        self.reference_level = 0
        self._tracked = False  # tracked insertions or deletions were met

    # parts ----------------------------------------------------------------------------------
    def _footnotes(self) -> dict[str, object]:
        for rel in self.doc.part.rels.values():
            if rel.reltype.endswith("/footnotes"):
                from lxml import etree

                root = etree.fromstring(rel.target_part.blob)
                return {fn.get(W + "id"): fn for fn in root.findall(W + "footnote")}
        return {}

    def _numbering(self) -> dict[tuple[str, str], str]:
        """(numId, ilvl) → numFmt from the numbering part."""
        formats: dict[tuple[str, str], str] = {}
        try:
            numbering = self.doc.part.numbering_part.element
        except (KeyError, NotImplementedError):
            return formats
        abstract = {}
        for an in numbering.findall(W + "abstractNum"):
            levels = {lvl.get(W + "ilvl"): (lvl.find(W + "numFmt").get(W + "val") if lvl.find(W + "numFmt") is not None else "bullet") for lvl in an.findall(W + "lvl")}
            abstract[an.get(W + "abstractNumId")] = levels
        for num in numbering.findall(W + "num"):
            ref = num.find(W + "abstractNumId")
            if ref is not None:
                for ilvl, fmt in abstract.get(ref.get(W + "val"), {}).items():
                    formats[(num.get(W + "numId"), ilvl)] = fmt
        return formats

    # inline ---------------------------------------------------------------------------------
    def _run(self, r) -> str:
        pieces = []
        for child in r:
            tag = child.tag
            if tag == W + "t":
                pieces.append(escape(child.text or ""))
            elif tag == W + "tab":
                pieces.append(r"\quad ")
            elif tag == W + "br":
                pieces.append("\n\n\\clearpage\n" if child.get(W + "type") == "page" else r"\newline ")
            elif tag == W + "footnoteReference":
                pieces.append(self._footnote(child.get(W + "id")))
            elif tag == W + "drawing":
                pieces.append(self._image(child))
            elif tag in (W + "object", W + "pict"):
                self.result.omitted += 1
                self.result.warnings.append("An embedded object (an old-style picture or OLE object) was left out; add it to the LaTeX by hand.")
                pieces.append("% embedded object not converted\n")
        text = "".join(pieces)
        if not text.strip() or text.startswith("\n"):
            return text
        rpr = r.find(W + "rPr")
        if rpr is not None:
            def on(tag: str) -> bool:
                el = rpr.find(W + tag)
                return el is not None and el.get(W + "val") not in ("0", "false", "none")

            valign = rpr.find(W + "vertAlign")
            if r.find(W + "footnoteReference") is not None:
                valign = None  # \footnote sets its own mark
            if valign is not None and valign.get(W + "val") == "superscript":
                text = r"\textsuperscript{%s}" % text
            elif valign is not None and valign.get(W + "val") == "subscript":
                text = r"\textsubscript{%s}" % text
            if on("u"):
                text = r"\underline{%s}" % text
            if on("i"):
                text = r"\emph{%s}" % text
            if on("b"):
                text = r"\textbf{%s}" % text
            if on("smallCaps"):
                text = r"\textsc{%s}" % text
        return text

    def _inline(self, container, in_math_para: bool = False) -> str:
        pieces = []
        for child in container:
            tag = child.tag
            if tag == W + "r":
                pieces.append(self._run(child))
            elif tag == W + "hyperlink":
                target = None
                rid = child.get(R + "id")
                if rid and rid in self.doc.part.rels and self.doc.part.rels[rid].is_external:
                    target = self.doc.part.rels[rid].target_ref
                text = self._inline(child)
                url = safe_url(target) if target else None
                pieces.append(r"\href{%s}{%s}" % (url, text) if url else text)
            elif tag in (W + "ins", W + "smartTag", W + "customXml", W + "fldSimple"):
                if tag == W + "ins":
                    self._tracked = True
                pieces.append(self._inline(child))
            elif tag in (W + "del", W + "moveFrom"):
                self._tracked = True
            elif tag == W + "sdt":
                content = child.find(W + "sdtContent")
                if content is not None:
                    pieces.append(self._inline(content))
            elif tag == M + "oMath":
                pieces.append(self._equation(child, display=False))
            elif tag == M + "oMathPara":
                for math in child.findall(M + "oMath"):
                    pieces.append(self._equation(math, display=True))
        return "".join(pieces)

    def _equation(self, math, display: bool) -> str:
        self.result.equations += 1
        try:
            body = _omml(math).strip()
        except Unsupported as exc:
            n = self.result.equations
            self.result.omitted += 1
            self.result.warnings.append(f"Equation {n} uses a structure the converter does not handle ({exc}); it is marked with a comment in main.tex. Retype it in LaTeX.")
            return f"\n% Equation {n} was not converted automatically: retype it here.\n"
        self.result.equations_converted += 1
        return f"\n\\[ {body} \\]\n" if display else f"${body}$"

    def _footnote(self, fid: str | None) -> str:
        note = self.footnotes.get(fid or "")
        if note is None:
            return ""
        text = " ".join(self._inline(p).strip() for p in note.findall(W + "p")).strip()
        return r"\footnote{%s}" % text

    def _image(self, drawing) -> str:
        blip = next(drawing.iter(A + "blip"), None)
        rid = blip.get(R + "embed") if blip is not None else None
        if not rid or rid not in self.doc.part.rels:
            return ""
        part = self.doc.part.rels[rid].target_part
        ext = part.partname.split(".")[-1].lower()
        if ext not in IMAGE_TYPES:
            self.result.omitted += 1
            self.result.warnings.append(f"An image in {ext.upper()} format was left out (LaTeX cannot use it directly); convert it to PNG and add it by hand.")
            return f"\n% image ({ext}) not converted\n"
        self.result.figures += 1
        name = f"figures/figure{self.result.figures}.{IMAGE_TYPES[ext]}"
        self.result.files[name] = part.blob
        return "\n\\begin{center}\n\\includegraphics[width=0.8\\linewidth,keepaspectratio]{%s}\n\\end{center}\n" % name

    # blocks ---------------------------------------------------------------------------------
    def _close_lists(self, depth: int = 0) -> None:
        while len(self.lists) > depth:
            self.out.append(f"\\end{{{self.lists.pop()}}}\n")

    def _list_item(self, p, style: str, text: str) -> bool:
        ppr = p.find(W + "pPr")
        num = ppr.find(W + "numPr") if ppr is not None else None
        if num is None and not style.startswith("List"):
            return False
        if num is not None:
            ilvl = num.find(W + "ilvl")
            numid = num.find(W + "numId")
            level = int(ilvl.get(W + "val")) if ilvl is not None else 0
            fmt = self.numbering.get((numid.get(W + "val") if numid is not None else "", str(level)), "bullet")
        else:
            level = int(re.sub(r"\D", "", style) or 1) - 1
            fmt = "decimal" if "Number" in style else "bullet"
        env = "itemize" if fmt in ("bullet", "none") else "enumerate"
        depth = min(level, 3) + 1
        self._close_lists(depth if len(self.lists) >= depth and self.lists[depth - 1] == env else depth - 1)
        while len(self.lists) < depth:
            self.lists.append(env)
            self.out.append(f"\\begin{{{env}}}\n")
        self.out.append(f"\\item {text}\n")
        return True

    def _paragraph(self, p) -> None:
        paragraph = Paragraph(p, self.doc._body)
        try:
            style = paragraph.style.name if paragraph.style is not None else "Normal"
        except (KeyError, ValueError):
            style = "Normal"
        text = self._inline(p).strip()
        plain = paragraph.text.strip()
        if not text:
            return
        if style == "Title" and not self.title:
            self._close_lists()
            self.title = text
            return
        level = None
        if style.startswith("Heading"):
            level = int(re.sub(r"\D", "", style) or 1)
        elif not self.in_references and len(plain.split()) <= 12:
            level = detect_fake_heading(paragraph, plain)
        if level:
            self._close_lists()
            if self.in_references and level <= self.reference_level:
                self.in_references = False
                self.out.append("\\end{list}\n")
            heading = MANUAL_NUMBER.sub("", text)
            if REFERENCES.match(plain):
                self.out.append(f"\n\\section*{{{heading}}}\n\\begin{{list}}{{}}{{\\leftmargin=1.27cm \\itemindent=-1.27cm \\itemsep=0.4em}}\n")
                self.in_references, self.reference_level = True, level
                return
            self.out.append(f"\n\\{SECTIONS.get(level, 'paragraph')}{{{heading}}}\n")
            return
        if self.in_references:
            self.out.append(f"\\item[] {text}\n")
            return
        if self._list_item(p, style, text):
            return
        self._close_lists()
        if "Quote" in style:
            self.out.append(f"\\begin{{quote}}\n{text}\n\\end{{quote}}\n")
        elif style == "Caption" or re.match(r"^(table|figure|fig\.)\s+\d+", plain, re.I):
            self.out.append(f"\\begin{{center}}\\emph{{{text}}}\\end{{center}}\n")
        else:
            self.out.append(f"{text}\n\n")

    def _table(self, tbl) -> None:
        self._close_lists()
        rows = tbl.findall(W + "tr")
        widths = []
        for tr in rows:
            widths.append(sum(int(tc.find(W + "tcPr").find(W + "gridSpan").get(W + "val")) if tc.find(W + "tcPr") is not None and tc.find(W + "tcPr").find(W + "gridSpan") is not None else 1 for tc in tr.findall(W + "tc")))
        columns = max(widths or [1])
        col = r"p{\dimexpr\linewidth/%d-2\tabcolsep-1pt\relax}" % columns
        lines = ["\\begin{center}\n\\begin{tabular}{|" + "|".join([col] * columns) + "|}\n\\hline\n"]
        for tr in rows:
            cells = []
            for tc in tr.findall(W + "tc"):
                if tc.find(W + "tbl") is not None:
                    self.result.warnings.append("A table inside a table was flattened to text; check its layout.")
                pr = tc.find(W + "tcPr")
                span_el = pr.find(W + "gridSpan") if pr is not None else None
                span = int(span_el.get(W + "val")) if span_el is not None else 1
                vmerge = pr.find(W + "vMerge") if pr is not None else None
                content = "" if vmerge is not None and vmerge.get(W + "val") in (None, "continue") else " \\newline ".join(
                    t for t in (self._inline(p).strip() for p in tc.iter(W + "p")) if t
                )
                cells.append(content if span == 1 else r"\multicolumn{%d}{|p{\dimexpr\linewidth*%d/%d-2\tabcolsep-1pt\relax}|}{%s}" % (span, span, columns, content))
            filled = sum(1 if not c.startswith(r"\multicolumn") else int(re.match(r"\\multicolumn\{(\d+)\}", c).group(1)) for c in cells)
            cells += [""] * (columns - filled)
            lines.append(" & ".join(cells) + " \\\\\n\\hline\n")
        lines.append("\\end{tabular}\n\\end{center}\n")
        self.out.append("".join(lines))

    def _walk(self, container) -> None:
        for child in container:
            if child.tag == W + "p":
                self._paragraph(child)
            elif child.tag == W + "tbl":
                self._table(child)
            elif child.tag == W + "sdt":
                content = child.find(W + "sdtContent")
                if content is not None:
                    self._walk(content)

    def convert(self) -> Result:
        self._walk(self.doc.element.body)
        self._close_lists()
        if self.in_references:
            self.out.append("\\end{list}\n")
        head = PREAMBLE + (f"\\title{{{self.title}}}\n\\author{{}}\n\\date{{}}\n" if self.title else "")
        body = "".join(self.out)
        self.result.tex = head + "\n\\begin{document}\n" + ("\\maketitle\n" if self.title else "") + "\n" + body + "\n\\end{document}\n"
        if self._tracked:
            self.result.warnings.append("The document has tracked changes; the LaTeX follows it with insertions kept and deletions removed. Check those passages.")
        return self.result


def convert(data: bytes) -> Result:
    return _Converter(data).convert()

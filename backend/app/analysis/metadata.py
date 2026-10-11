"""A source's bibliographic details, made fit to print.

Publishers register what they send: an affiliation in an author's place, names and titles in capitals, a degree
inside a surname, markup and entities in a title ("<scp>ICT</scp>", "&amp;"). PaperAid copied those records as they
were (the audit of the trial documents, 2026-10-10: "Faculty of Business and Management, Universiti Teknologi MARA,
Malaysia" printed as an author, "MIROGA (PhD), D. J.", "Economics &amp; Finance"). These functions clean a record
when it is fetched and again when a reference is printed, so evidence saved earlier is printed correctly too.
Nothing here invents a detail: an entry is dropped or tidied, never guessed."""

import html
import re

_TAG = re.compile(r"</?[A-Za-z][^<>]{0,60}>")
_DEGREE = re.compile(r"\s*\(\s*(?:Ph\.?\s?D\.?|D\.?Phil\.?|Dr\.?|Prof\.?|M\.?Sc\.?|M\.?A\.?|MBA|M\.?D\.?|MPH|B\.?Sc\.?|Eng\.?|CPA)\s*\)", re.I)
_TITLE_BEFORE = re.compile(r"^(?:Dr|Prof|Professor|Assoc\. Prof|Rev|Mr|Mrs|Ms)\.?\s+", re.I)
# An entry that is where an author works, not who the author is.
_AFFILIATION = re.compile(r"\b(?:department|dept|faculty|school of|college of|universit\w*|institut\w*|centre for|center for|hospital|laborator\w+|division of|campus)\b", re.I)
_PERSON = re.compile(r"^[^,;]{1,40},\s*(?:[^\W\d_]\.\s?){1,6}$")  # "Okello, J. P."
# Where a copy is kept, not where the work was published: never printed as the journal.
_REPOSITORY = re.compile(r"\b(?:repositor\w+|RePEc|research archive|IRDB|DSpace|ePrints?|digital commons|institutional archive)\b", re.I)
# A registered author that is a body, not a person.
_ORGANISATION = re.compile(
    r"\b(?:cent(?:re|er)|institut\w*|universit\w*|ministry|bureau|organi[sz]ation|association|society|council|commission|authority|agency|department|office"
    r"|foundation|bank|fund|programme|program|committee|group|network|alliance|partnership|initiative|consortium|collaborat\w+|team|government|secretariat|union"
    r"|trust|limited|ltd|inc|technologies|solutions|labs?|press|news|radio|school|college|hospital|library|unicef|unesco)\b|[()&]|\b(?:for|of|the|and)\b", re.I)
_SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with", "among", "between"}


def clean_text(value: str) -> str:
    """Registered text without the markup and entities it was stored with, its spaces put right. Entities are
    undone twice at most: "&amp;lt;b&amp;gt;" is markup that was escaped twice."""
    text = value or ""
    for _ in range(2):
        text = _TAG.sub("", html.unescape(text))
    return " ".join(text.split())


def _shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.85


def _title_case(text: str) -> str:
    words = text.split(" ")
    out = []
    for n, word in enumerate(words):
        lower = word.lower()
        out.append(lower if n and lower.strip(",.:;") in _SMALL and not words[n - 1].endswith(":") else lower[:1].upper() + lower[1:])
    return " ".join(out)


def clean_title(value: str) -> str:
    """A title as printed: no markup, and not in capitals throughout (a title registered in capitals keeps a capital
    on each main word, so the names of places and people in it stay right)."""
    text = clean_text(value)
    return _title_case(text) if _shouting(text) else text


def clean_container(value: str) -> str:
    """The journal or publication a work appeared in, as printed: no markup, no full stop of its own (the reference
    adds the punctuation), not in capitals throughout unless it is a short name of initials ("PLOS ONE"), and nothing
    at all when what was registered is a repository that only keeps a copy."""
    text = clean_text(value).rstrip(" .,;")
    if _REPOSITORY.search(text):
        return ""
    return _title_case(text) if _shouting(text) and any(len(word) > 5 for word in re.findall(r"[^\W\d_]+", text)) else text


def clean_pages(value: str) -> str:
    """ "105–105" is one page (an article number registered as both ends of a range)."""
    first, dash, last = (value or "").partition("–")
    return first.strip() if dash and first.strip() == last.strip() else (value or "")


def is_organisation(name: str) -> bool:
    """A registered author that is a body ("Center for Rapid Evidence Synthesis (ACRES)"): its name is kept whole,
    never split into a surname and initials."""
    return bool(_ORGANISATION.search(name))


def distinct_people(names: list[str]) -> list[str]:
    """Full names with nobody twice: some records list each author again with the names in the other order
    ("Conrad Murendo" and "Murendo Conrad"), which printed as two people."""
    seen: set[frozenset[str]] = set()
    out = []
    for name in names:
        words = frozenset(re.findall(r"[^\W\d_]+", name.casefold()))
        if words and words in seen:
            continue
        seen.add(words)
        out.append(name)
    return out


def clean_authors(authors: list[str]) -> list[str]:
    """The people (or the one organisation) who wrote a work, from what was registered as its authors. A degree or
    title is not part of a name; a surname in capitals is written normally; nobody is listed twice. Where the record
    names people, an entry that is a place of work is not an author. Where it names only an organisation, that is the
    author (a ministry, an agency), and stays."""
    cleaned: list[str] = []
    for raw in authors:
        name = _TITLE_BEFORE.sub("", _DEGREE.sub("", clean_text(raw))).strip(" ,;")
        if not name:
            continue
        family, comma, rest = name.partition(",")
        if comma and family.endswith(".") and _PERSON.match(f"{family.rstrip('.')},{rest}"):  # "Han., C. S.": a full stop registered inside the surname
            family = family.rstrip(".")
            name = f"{family},{rest}"
        if comma and _shouting(family) and len(family.strip()) > 3 and _PERSON.match(f"{family},{rest}"):
            name = f"{_title_case(family.strip())},{rest}"
        cleaned.append(name)
    people = [a for a in cleaned if _PERSON.match(a)]
    if people:  # places of work registered among the people who wrote it
        cleaned = [a for a in cleaned if _PERSON.match(a) or not (_AFFILIATION.search(a) or len(a) > 80)]
    seen: set[str] = set()
    return [a for a in cleaned if not (a.casefold() in seen or seen.add(a.casefold()))]

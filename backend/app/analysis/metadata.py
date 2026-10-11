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
# An entry that is where an author works, not who the author is: a unit or an institution written with what it
# belongs to or where it is, after a comma ("Department of ..., University of ..., Malaysia"). A body named on its own
# ("National Cancer Institute", "Department of Health", "RTS,S Clinical Trials Partnership") can be a genuine group
# author and is kept (Codex's audits of 1a3b1e7, finding 4, and of 458e65b, finding 2).
_UNIT = re.compile(r"\b(?:department|dept|faculty|school of|college of|division of|unit of|section of|laborator\w+ of|campus)\b", re.I)
_PLACE = re.compile(r"\b(?:universit\w*|institut\w*|college|hospital|cent(?:re|er))\b", re.I)
_PERSON = re.compile(r"^[^,;]{1,40},\s*(?:[^\W\d_]\.\s?){1,6}$")  # "Okello, J. P."
# Where a copy is kept, not where the work was published: never printed as the journal. Only names that say so
# outright; an index's own record of the source type decides first (`fetch._openalex_works`).
_REPOSITORY = re.compile(r"\bRePEc\b|\bDSpace\b|\bePrints?\b|\bRepositories DataBase\b|\binstitutional\s+repositor\w+\b|\b(?:repository|research archive)\s*(?:\([^()]*\))?$", re.I)
# A registered author that is a body, not a person: a word only bodies carry, or the small words inside a body's name.
_ORGANISATION = re.compile(
    r"\b(?:cent(?:re|er)|institut\w*|universit\w*|ministry|bureau|organi[sz]ation|association|society|council|commission|authority|agency|department|office"
    r"|foundation|bank|fund|programme|program|committee|group|network|alliance|partnership|initiative|consortium|collaborat\w+|team|government|secretariat|union"
    r"|trust|limited|ltd|inc|technologies|solutions|labs?|press|news|radio|school|college|hospital|library|unicef|unesco)\b|&", re.I)
_BODY_WORDS = re.compile(r"(?<=\s)(?:for|of|the|and)(?=\s)")  # lower case only: a surname "The" or "Of" is written with a capital
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


def without_markers(name: str) -> str:
    """An author's name without the affiliation markers a page prints against it ("Figueiredo1,2")."""
    return re.sub(r"(?<=[^\W\d_])\d+(?:\s*,\s*\d+)*\b", "", name).strip(" ,;")


def bare_site(title: str) -> bool:
    """A "title" that is only a site's address ("eprcug.org"): not the title of anything."""
    return not title.strip() or bool(re.fullmatch(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}/?", title.strip(), re.I))


def is_organisation(name: str) -> bool:
    """A registered author that is a body ("Center for Rapid Evidence Synthesis (ACRES)"): its name is kept whole,
    never split into a surname and initials. Used only where the record does not say which an author is; brackets
    alone decide nothing ("John (Jack) Smith" is a person)."""
    return bool(_ORGANISATION.search(name) or _BODY_WORDS.search(name))


def _words(name: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", name.casefold())


def _turned(a: list[str], b: list[str]) -> bool:
    """The same name with its parts in the other order: "conrad murendo" and "murendo conrad", "lwanga mayanja musa" and "musa lwanga mayanja"."""
    return len(a) >= 2 and a != b and any(a[k:] + a[:k] == b for k in range(1, len(a)))


def distinct_people(names: list[str], ids: list[str] | None = None) -> list[str]:
    return [names[n] for n in distinct_entries(names, ids)]


def distinct_entries(names: list[str], ids: list[str] | None = None) -> list[int]:
    """The positions to keep of full names as registered. An entry is dropped only where the record itself shows it
    is a second entry of somebody already listed, and never when the record gives the two entries different
    identifiers (Codex's audits of 1a3b1e7 and 458e65b):

    - the same full name again, unless both entries carry identifiers and they differ;
    - an entry with no identifier whose name is that of an identified author with its parts the other way round. This
      is how the fault is actually registered: "Conrad Murendo" and "Meike Wollni", each with an identifier, followed
      by "Murendo, Conrad" and "Wollni, Meike" with none;
    - where no entry in it carries an identifier, the whole list entered a second time the other way round.

    Nothing else is inferred. "John Paul" and "Paul John" with two identifiers, or with none in a list that is not a
    repeat of itself, are two authors, and so are two people who share a surname and initials."""
    known = ids if ids is not None and len(ids) == len(names) else [""] * len(names)
    words = [_words(name) for name in names]
    half = len(names) // 2
    count = len(names)
    if len(names) >= 4 and len(names) % 2 == 0 and not any(known[half:]) and all(_turned(a, b) for a, b in zip(words[:half], words[half:], strict=True)):
        count = half
    out: list[int] = []
    seen: dict[str, set[str]] = {}
    for n in range(count):
        same = " ".join(names[n].casefold().split())
        if same and same in seen and not (known[n] and seen[same] and known[n] not in seen[same]):
            continue
        if not known[n] and any(known[other] and _turned(words[other], words[n]) for other in range(len(names)) if other != n):
            continue
        seen.setdefault(same, set())
        if known[n]:
            seen[same].add(known[n])
        out.append(n)
    return out


def _affiliation(entry: str) -> bool:
    """A unit or an institution given with what it belongs to or where it is ("Department of Epidemiology, National
    Cancer Institute, Bethesda"). A body named on its own, a department included ("Department of Health"), can be a
    group author and is kept."""
    return ("," in entry and bool(_UNIT.search(entry) or _PLACE.search(entry))) or len(entry) > 120


def clean_authors(authors: list[str]) -> list[str]:
    """The people and bodies who wrote a work, from what was registered as its authors. A degree or title is not part
    of a name and a surname in capitals is written normally. Where the record names people, an entry that is a place
    of work (a department, a faculty, an institution with its town) is not an author; a body named on its own beside
    them is a group author and stays. Nobody is merged with anybody: two authors whose names shorten alike are two."""
    cleaned: list[str] = []
    for raw in authors:
        name = _TITLE_BEFORE.sub("", _DEGREE.sub("", clean_text(raw))).strip(" ,;")
        name = re.sub(r"^(?:for|on behalf of)\s+(?:the\s+)?(?=[A-Z])", "", name)  # "for the STROBE Initiative": the group is the author
        if not name:
            continue
        family, comma, rest = name.partition(",")
        if comma and family.endswith(".") and _PERSON.match(f"{family.rstrip('.')},{rest}"):  # "Han., C. S.": a full stop registered inside the surname
            family = family.rstrip(".")
            name = f"{family},{rest}"
        if comma and _shouting(family) and len(family.strip()) > 3 and _PERSON.match(f"{family},{rest}"):
            name = f"{_title_case(family.strip())},{rest}"
        cleaned.append(name)
    if any(_PERSON.match(a) for a in cleaned):  # places of work registered among the people who wrote it
        cleaned = [a for a in cleaned if _PERSON.match(a) or not _affiliation(a)]
    seen: set[str] = set()
    out = []
    for name in cleaned:  # a body entered twice is one body; a person's shortened name proves nothing about a second person
        if not _PERSON.match(name):
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
        out.append(name)
    return out

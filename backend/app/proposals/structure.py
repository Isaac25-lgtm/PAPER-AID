"""One guide and rulebook check shared by submission and final publication."""

from app.core.errors import AppError
from app.proposals import rulebook
from app.proposals.models import Project, StepInput, moved_path


def guide_read(p: Project) -> bool:
    """Whether the project's current profile was read from its current guide."""
    try:
        book = rulebook.load(p.rulebook)
    except AppError as exc:
        if exc.code != "PROFILE_MISSING":
            raise
        return False
    return p.guide is not None and book.get("guide_sha256") == p.guide.sha256


def structure_current(p: Project, inp: StepInput) -> bool:
    """A step may run only on the guide and structure frozen when it was priced."""
    if inp.step == "PROFILE":
        return p.guide is not None and p.guide.path in (inp.guide, moved_path(inp.guide))
    if p.rulebook != inp.rulebook:
        return False
    if inp.guide_sha256 is not None and (p.guide.sha256 if p.guide else "") != inp.guide_sha256:
        return False
    return p.guide is None or any(c.versions for c in p.chapters) or guide_read(p)

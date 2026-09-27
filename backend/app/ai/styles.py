"""Writing styles and intervention levels (owner decision 2026-09-27), as the plan and the writer
receive them. The style is part of the priced selection, so a job always runs with the style it
was quoted for. No style permits new facts, new technical detail or a stronger claim."""

from app.jobs.models import WritingStyle

STYLE_LABELS: dict[WritingStyle, str] = {
    "PRESERVE_VOICE": "Preserve my voice",
    "STANDARD_ACADEMIC": "Standard academic",
    "CONCISE_ACADEMIC": "Concise academic",
    "TECHNICAL": "Technical/scientific",
}

_STYLES: dict[WritingStyle, str] = {
    "PRESERVE_VOICE": (
        "Preserve my voice: keep the student's own vocabulary, sentence habits, register and perspective wherever they are sound, "
        "and change only what the instruction targets. Someone who knows the student's writing should recognise the result as theirs."
    ),
    "STANDARD_ACADEMIC": (
        "Standard academic: clear, formal academic English at the level of a good university paper; neutral register, precise verbs, "
        "no colloquialisms. Keep the student's argument and perspective."
    ),
    "CONCISE_ACADEMIC": (
        "Concise academic: formal academic English without filler. Cut redundancy and wordiness and prefer direct sentences where the "
        "meaning allows, but never cut evidence, content or a qualification the claim depends on."
    ),
    "TECHNICAL": (
        "Technical/scientific: a precise, plain technical register for science, engineering and health writing. Use exact terms "
        "consistently and keep claims measured. Never add technical detail, units, mechanisms or values that are not already in the passage."
    ),
}
_ALWAYS = "Whatever the style: no new facts, no new technical detail, and no claim made stronger, wider or more certain than the student made it."

_INTENSITY = {
    "LIGHT": "Light: fix the problems found with the smallest change that works; leave the structure and most of the wording as it is.",
    "STANDARD": (
        "Standard: improve flow, reduce formulaic language, vary sentence structure and strengthen the academic tone within each passage, "
        "keeping its argument, the order of its ideas and its claims."
    ),
}


def writing_brief(style: WritingStyle, intensity: str) -> dict[str, str]:
    """The style and intervention constraints, as every planning and writing step receives them."""
    return {"style": f"{_STYLES[style]} {_ALWAYS}", "intervention": _INTENSITY.get(intensity, _INTENSITY["STANDARD"])}

"""Published Vertex Standard/Global rates (USD per million tokens), checked on Google's pricing page.

Gemini 3.8 Flash was verified 2026-10-06; Gemini 3.5 Flash-Lite and Gemini 3.1 Pro Preview 2026-10-07.
Quotes freeze one flat record, never this schedule, so a price change never moves an existing quote.
The $300 Google Cloud credit pays Google's bill; it is not a model rate and is never used here.
"""

from datetime import date

from app.ai.gemini import GroundingPrice, VertexPrice

SOURCE = "https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing"
SEARCH = GroundingPrice(
    source=SOURCE, free_queries_per_month=5_000,
    allowance_scope="Aggregated across all Gemini 3 models in the billing account; not per job or student",
    excess_usd_per_1000_queries=14,
)
FLASH_INTRO = VertexPrice(
    status="VERIFIED", source=SOURCE, input=0.75, output=3.75, cached=0.075,
    effective_from=date(2026, 10, 6), effective_until=date(2026, 12, 31),
    verified_on=date(2026, 10, 6), location="global", grounding=SEARCH,
    pricing_note="Published introductory pricing through 2026-12-31, provided as 50% credits back on net spend. "
                 "Confirm on the billing statement; unrelated to the $300 Cloud credit.",
)
FLASH = VertexPrice(
    status="VERIFIED", source=SOURCE, input=1.50, output=7.50, cached=0.15,
    effective_from=date(2027, 1, 1), verified_on=date(2026, 10, 6), location="global", grounding=SEARCH,
)
FLASH_LITE = VertexPrice(
    status="VERIFIED", source=SOURCE, input=0.30, output=2.50, cached=0.03,
    effective_from=date(2026, 10, 6), verified_on=date(2026, 10, 7), location="global", grounding=SEARCH,
)
PRO_PREVIEW = VertexPrice(
    status="VERIFIED", source=SOURCE, input=2.00, output=12.00, cached=0.20,
    long_context_tokens=200_000, long_input=4.00, long_output=18.00, long_cached=0.40,
    effective_from=date(2026, 10, 6), verified_on=date(2026, 10, 7), location="global", grounding=SEARCH,
)
VERIFIED_VERTEX_PRICES = {
    "gemini-3.8-flash": FLASH_INTRO.model_copy(update={"schedule": (FLASH_INTRO, FLASH)}),
    "gemini-3.5-flash-lite": FLASH_LITE,
    "gemini-3.1-pro-preview": PRO_PREVIEW,
}

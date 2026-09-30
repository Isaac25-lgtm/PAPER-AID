"""Versioned model price tables (USD per million tokens) and the per-job budget guard.

Prices change on known dates (Gemini 3.8 Flash's introductory rates end on 1 January 2027), so the
tables are dated. A work step's quote freezes the table in force when it was priced: its spend
projection and cap never move afterwards (Codex review 2026-09-30 #5). What a call actually cost is
recorded at the table in force when it was made. "" means the table in force today."""

from datetime import date

from app.core.errors import PermanentStageError

PRICE_TABLE_VERSION = "2026-09"

# (uncached input, output, cached input), standard short-context rates. A model without
# an explicit price is unavailable: a guessed rate would make the cost guard unreliable.
PRICES: dict[str, tuple[float, float, float]] = {
    "openai:gpt-6-sol": (2.0, 10.0, 0.20),
    "openai:gpt-6-luna": (0.10, 0.50, 0.01),
    "anthropic:claude-opus-5-5": (4.0, 20.0, 0.20),
    "anthropic:claude-opus-5": (5.0, 25.0, 0.50),
    "anthropic:claude-sonnet-5": (2.0, 10.0, 0.20),
    "anthropic:claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "anthropic:claude-haiku-4-5": (1.0, 5.0, 0.10),
    # Introductory rates (Google's model documentation, checked 2026-09-30). Output includes thinking
    # tokens. No cached-input rate is relied on: cached input is costed as input, never undercounted.
    "google:gemini-3.8-flash": (0.75, 3.75, 0.75),
}
Prices = dict[str, tuple[float, float, float]]
# Each table applies from its date; Gemini 3.8 Flash's standard rates double on 1 January 2027.
PRICE_TABLES: dict[str, Prices] = {
    "2026-09": PRICES,
    "2027-01": {**PRICES, "google:gemini-3.8-flash": (1.50, 7.50, 1.50)},
}
TABLE_FROM: dict[str, date] = {"2026-09": date(2026, 9, 1), "2027-01": date(2027, 1, 1)}


def table_in_force(on: date | None = None) -> str:
    today = on or date.today()
    return max((v for v, start in TABLE_FROM.items() if start <= today), key=lambda v: TABLE_FROM[v], default=PRICE_TABLE_VERSION)


def price_for(provider: str, model: str, overrides: Prices | None = None, table: str = "") -> tuple[float, float, float]:
    key = f"{provider}:{model}"
    price = (overrides or {}).get(key) or PRICE_TABLES[table or table_in_force()].get(key)
    if price is None:
        raise PermanentStageError("MODEL_PRICE_NOT_CONFIGURED", "AI pricing is not configured for this model.", f"model={key}")
    return price


# Writing input to the prompt cache costs 1.25x the input price on both providers
# (Anthropic 5-minute cache writes; OpenAI GPT-6 Sol lists $2.50 against $2 input).
CACHE_WRITE_MULTIPLIER = 1.25


# Web search: a fee per search, plus the pages it reads, which arrive as ordinary input tokens in
# the provider's usage. OpenAI: $10 per 1,000 searches (pricing page checked 2026-09-27). Only the
# lead searches (the writer checks what it found), so only the lead's provider needs a fee here.
SEARCH_FEE_USD: dict[str, float] = {"openai": 0.01}
# Input to reserve per search at "medium" search context before a search call is made. Two
# searches measured 13–17k tokens in total (2026-09-27); OpenAI states the setting "does not set an
# exact token count", so this is a generous reserve, not a guarantee (Codex audit #6).
SEARCH_INPUT_TOKENS_WORST = 20_000
# Characters of request around the paper data that the character count does not see: the data
# wrapper, the answer format (JSON schema) and message framing.
REQUEST_OVERHEAD_CHARS = 2_000
# Worst-case characters per token for the ceiling: English is about 4, dense or non-Latin text can
# be near 2. Estimates elsewhere use 3.5; the ceiling uses this.
CEILING_CHARS_PER_TOKEN = 2.0


def search_fee_usd(provider: str, searches: int) -> float:
    if searches and provider not in SEARCH_FEE_USD:
        raise PermanentStageError("SEARCH_PRICE_NOT_CONFIGURED", "AI pricing is not configured for web search.", f"provider={provider}")
    return searches * SEARCH_FEE_USD.get(provider, 0.0)


def cost_usd(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    overrides: Prices | None = None,
    cache_write_tokens: int = 0,
    search_calls: int = 0,
    table: str = "",
) -> float:
    inp, out, cached = price_for(provider, model, overrides, table)
    tokens = (input_tokens * inp + cache_write_tokens * inp * CACHE_WRITE_MULTIPLIER + output_tokens * out + cached_tokens * cached) / 1_000_000
    return tokens + search_fee_usd(provider, search_calls)


MIN_OUTPUT_TOKENS = 2000  # below this a structured answer can't be useful: stop instead of calling


def affordable_output_tokens(
    provider: str, model: str, prompt_chars: int, max_output_tokens: int, remaining_usd: float, overrides: Prices | None = None, table: str = ""
) -> int:
    """The most output a call may produce so that its worst case stays within the remaining budget:
    the whole request (plus framing) counted at 2 characters per token and billed as a cache write
    (the dearest input), plus every output token. Output is therefore capped exactly; the input
    side is a conservative bound, not an exact count: a call whose text packs more than one token
    per two characters could still overshoot by that difference, which PaperAid absorbs (the
    student is never charged above the quote)."""
    inp, out, _ = price_for(provider, model, overrides, table)
    if out <= 0:
        return max_output_tokens
    worst_input_tokens = (prompt_chars + REQUEST_OVERHEAD_CHARS) / CEILING_CHARS_PER_TOKEN
    worst_input_usd = worst_input_tokens * inp * CACHE_WRITE_MULTIPLIER / 1_000_000
    return max(0, min(max_output_tokens, int((remaining_usd - worst_input_usd) * 1_000_000 / out)))


THINKING_ALLOWANCE_TOKENS = 3000


def estimate_usd(provider: str, model: str, prompt_chars: int, max_output_tokens: int, overrides: Prices | None = None, table: str = "") -> float:
    """Realistic high estimate of a call's cost before making it (about 3.5 characters per token).
    Output is sized to the input (a rewrite is roughly as long as its source) plus room for the
    model's thinking, capped at the call's output limit."""
    inp, out, _ = price_for(provider, model, overrides, table)
    input_tokens = prompt_chars / 3.5
    expected_output = min(max_output_tokens, input_tokens * 1.3 + THINKING_ALLOWANCE_TOKENS)
    return (input_tokens * inp + expected_output * out) / 1_000_000


def ensure_within_budget(spent: float, estimate: float, budget: float) -> None:
    if spent + estimate > budget:
        raise PermanentStageError(
            "BUDGET_EXCEEDED",
            "This job needed more processing than its quote allowed, so we stopped it safely. Your credits were returned.",
            f"spent={spent:.4f} estimate={estimate:.4f} budget={budget:.4f}",
        )

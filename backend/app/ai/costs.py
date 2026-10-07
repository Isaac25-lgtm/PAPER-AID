"""Versioned model price tables (USD per million tokens) and the per-job budget guard.

Prices change on known dates (Gemini 3.8 Flash's introductory rates end on 1 January 2027), so the
tables are dated. A work step's quote freezes the table in force when it was priced: its spend
projection and cap never move afterwards (Codex review 2026-09-30 #5). What a call actually cost is
recorded at the table in force when it was made. "" means the table in force today."""

from datetime import date
from decimal import Decimal

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
        if provider == "vertex":
            raise PermanentStageError("VERTEX_PRICING_UNVERIFIED", "AI pricing is not configured for Vertex.", f"unverified price for {key}")
        raise PermanentStageError("MODEL_PRICE_NOT_CONFIGURED", "AI pricing is not configured for this model.", f"model={key}")
    return price


LongPrices = dict[str, tuple[int, float, float, float]]


def rates_for(provider: str, model: str, input_tokens: float, overrides: Prices | None = None, table: str = "",
              long_prices: LongPrices | None = None) -> tuple[float, float, float]:
    """The rates a request of this many input tokens is billed at: a model priced in two context tiers
    (Gemini Pro on Vertex) bills the whole request at its long-context rates above the threshold."""
    rates = price_for(provider, model, overrides, table)
    tier = (long_prices or {}).get(f"{provider}:{model}")
    if tier and input_tokens > tier[0]:
        return tier[1], tier[2], tier[3]
    return rates


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


def search_fee_usd(provider: str, searches: int, unit_prices: dict[str, float] | None = None, model: str = "") -> float:
    if provider == "vertex" and searches:
        key = f"vertex:{model}:google_search_query"
        if key not in (unit_prices or {}):
            raise PermanentStageError("VERTEX_PRICING_UNVERIFIED", "AI pricing is not configured for web search.", "Vertex grounding fee unverified")
        return searches * unit_prices[key]
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
    billable_units: dict[str, float] | None = None,
    unit_prices: dict[str, float] | None = None,
    long_prices: LongPrices | None = None,
) -> float:
    inp, out, cached = rates_for(provider, model, input_tokens + cached_tokens, overrides, table, long_prices)
    if provider == "vertex":
        tokens = vertex_token_cost(input_tokens, output_tokens, cached_tokens, (inp, out, cached), cache_write_tokens)
        units = dict(billable_units or {})
        if search_calls:
            units.setdefault("google_search_query", search_calls)
        for unit, count in units.items():
            key = f"vertex:{model}:{unit}"
            if key not in (unit_prices or {}):
                raise PermanentStageError("VERTEX_PRICING_UNVERIFIED", "AI pricing is not configured.", f"unpriced Vertex unit {unit}")
            tokens += Decimal(str(count)) * Decimal(str(unit_prices[key]))
        return float(tokens)  # existing ledger boundary; retain sub-microdollar precision per call
    tokens = (input_tokens * inp + cache_write_tokens * inp * CACHE_WRITE_MULTIPLIER + output_tokens * out + cached_tokens * cached) / 1_000_000
    return tokens + search_fee_usd(provider, search_calls)


def vertex_token_cost(input_tokens: int, billable_output_tokens: int, cached_tokens: int,
                      rates: tuple[float, float, float], cache_write_tokens: int = 0) -> Decimal:
    """Exact token cost. Output already includes thinking: never add it here again.

    Explicit cache creation/storage is not implemented by the Vertex adapter; never
    borrow another provider's cache-write multiplier for an actual Vertex charge.
    """
    if cache_write_tokens:
        raise PermanentStageError("VERTEX_PRICING_UNVERIFIED", "AI pricing is not configured.", "Vertex cache creation is not priced")
    inp, out, cached = (Decimal(str(rate)) for rate in rates)
    return (Decimal(input_tokens) * inp + Decimal(billable_output_tokens) * out + Decimal(cached_tokens) * cached) / Decimal(1_000_000)


MIN_OUTPUT_TOKENS = 2000  # below this a structured answer can't be useful: stop instead of calling


def affordable_output_tokens(
    provider: str, model: str, prompt_chars: int, max_output_tokens: int, remaining_usd: float, overrides: Prices | None = None, table: str = "",
    long_prices: LongPrices | None = None,
) -> int:
    """The most output a call may produce so that its worst case stays within the remaining budget:
    the whole request (plus framing) counted at 2 characters per token, at uncached input for
    Vertex (no explicit cache creation) or cache-write rates for legacy providers, plus every
    output token. Output is therefore capped exactly; the input
    side is a conservative bound, not an exact count: a call whose text packs more than one token
    per two characters could still overshoot by that difference, which PaperAid absorbs (the
    student is never charged above the quote)."""
    worst_input_tokens = (prompt_chars + REQUEST_OVERHEAD_CHARS) / CEILING_CHARS_PER_TOKEN
    inp, out, _ = rates_for(provider, model, worst_input_tokens, overrides, table, long_prices)
    if out <= 0:
        return max_output_tokens
    input_multiplier = 1.0 if provider == "vertex" else CACHE_WRITE_MULTIPLIER
    worst_input_usd = worst_input_tokens * inp * input_multiplier / 1_000_000
    return max(0, min(max_output_tokens, int((remaining_usd - worst_input_usd) * 1_000_000 / out)))


THINKING_ALLOWANCE_TOKENS = 3000


def estimate_usd(provider: str, model: str, prompt_chars: int, max_output_tokens: int, overrides: Prices | None = None, table: str = "",
                 long_prices: LongPrices | None = None, thinking_tokens: int = THINKING_ALLOWANCE_TOKENS) -> float:
    """Realistic high estimate of a call's cost before making it (about 3.5 characters per token).
    Output is sized to the input (a rewrite is roughly as long as its source) plus room for the
    model's thinking, capped at the call's output limit. The context tier is chosen on the
    worst-case token count, so a request near a tier threshold is estimated at the dearer rates."""
    inp, out, _ = rates_for(provider, model, (prompt_chars + REQUEST_OVERHEAD_CHARS) / CEILING_CHARS_PER_TOKEN, overrides, table, long_prices)
    input_tokens = prompt_chars / 3.5
    expected_output = min(max_output_tokens, input_tokens * 1.3 + thinking_tokens)
    return (input_tokens * inp + expected_output * out) / 1_000_000


def ensure_within_budget(spent: float, estimate: float, budget: float) -> None:
    if spent + estimate > budget:
        raise PermanentStageError(
            "BUDGET_EXCEEDED",
            "This job needed more processing than its quote allowed, so we stopped it safely. Your credits were returned.",
            f"spent={spent:.4f} estimate={estimate:.4f} budget={budget:.4f}",
        )

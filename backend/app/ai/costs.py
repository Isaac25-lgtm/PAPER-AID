"""Versioned model price table (USD per million tokens) and the per-job budget guard."""

from app.core.errors import PermanentStageError

PRICE_TABLE_VERSION = "2026-09"

# (uncached input, output, cached input), standard short-context rates. A model without
# an explicit price is unavailable: a guessed rate would make the cost guard unreliable.
PRICES: dict[str, tuple[float, float, float]] = {
    "openai:gpt-6-sol": (2.0, 10.0, 0.20),
    "anthropic:claude-opus-5-5": (4.0, 20.0, 0.20),
    "anthropic:claude-opus-5": (5.0, 25.0, 0.50),
    "anthropic:claude-sonnet-5": (2.0, 10.0, 0.20),
    "anthropic:claude-haiku-4-5": (1.0, 5.0, 0.10),
}
Prices = dict[str, tuple[float, float, float]]


def price_for(provider: str, model: str, overrides: Prices | None = None) -> tuple[float, float, float]:
    key = f"{provider}:{model}"
    price = (overrides or {}).get(key) or PRICES.get(key)
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
# The most input one search can add at "medium" search context (two searches measured 13–17k
# tokens in total on 2026-09-27); used for the hard ceiling before a search call is made.
SEARCH_INPUT_TOKENS_WORST = 12_000


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
) -> float:
    inp, out, cached = price_for(provider, model, overrides)
    tokens = (input_tokens * inp + cache_write_tokens * inp * CACHE_WRITE_MULTIPLIER + output_tokens * out + cached_tokens * cached) / 1_000_000
    return tokens + search_fee_usd(provider, search_calls)


MIN_OUTPUT_TOKENS = 2000  # below this a structured answer can't be useful: stop instead of calling


def affordable_output_tokens(provider: str, model: str, prompt_chars: int, max_output_tokens: int, remaining_usd: float, overrides: Prices | None = None) -> int:
    """The most output a call may produce so that even its worst case stays within the remaining
    budget: the whole prompt billed as a cache write (the dearest input), plus every output token.
    This makes the job's provider-spend cap a hard ceiling, not an estimate."""
    inp, out, _ = price_for(provider, model, overrides)
    if out <= 0:
        return max_output_tokens
    worst_input_usd = (prompt_chars / 3.0) * inp * CACHE_WRITE_MULTIPLIER / 1_000_000  # 3 chars/token: generous
    return max(0, min(max_output_tokens, int((remaining_usd - worst_input_usd) * 1_000_000 / out)))


THINKING_ALLOWANCE_TOKENS = 3000


def estimate_usd(provider: str, model: str, prompt_chars: int, max_output_tokens: int, overrides: Prices | None = None) -> float:
    """Realistic high estimate of a call's cost before making it (about 3.5 characters per token).
    Output is sized to the input (a rewrite is roughly as long as its source) plus room for the
    model's thinking, capped at the call's output limit."""
    inp, out, _ = price_for(provider, model, overrides)
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

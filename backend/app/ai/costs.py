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


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int, cached_tokens: int, overrides: Prices | None = None) -> float:
    inp, out, cached = price_for(provider, model, overrides)
    return (input_tokens * inp + output_tokens * out + cached_tokens * cached) / 1_000_000


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

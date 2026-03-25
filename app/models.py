"""Qwen model definitions, aliases, and token limits."""

from .config import DEFAULT_MODEL

MODEL_ALIASES: dict[str, str] = {"qwen3.5-plus": "coder-model"}

MODELS: list[dict[str, str | int]] = [
    {
        "id": "qwen3-coder-plus",
        "object": "model",
        "created": 1754686206,
        "owned_by": "qwen",
    },
    {
        "id": "qwen3-coder-flash",
        "object": "model",
        "created": 1754686206,
        "owned_by": "qwen",
    },
    {"id": "coder-model", "object": "model", "created": 1754686206, "owned_by": "qwen"},
    {
        "id": "vision-model",
        "object": "model",
        "created": 1754686206,
        "owned_by": "qwen",
    },
]

MODEL_MAX_TOKENS: dict[str, int] = {
    "vision-model": 32768,
    "qwen3-vl-plus": 32768,
    "qwen3-vl-max": 32768,
}


def resolve_model(model: str) -> str:
    return MODEL_ALIASES.get(model, model) or DEFAULT_MODEL


def clamp_max_tokens(model: str, max_tokens: int) -> int:
    limit = MODEL_MAX_TOKENS.get(model)
    if limit and max_tokens > limit:
        return limit
    return max_tokens

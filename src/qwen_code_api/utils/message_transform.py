"""Message transformations: system prompt injection and cache_control tagging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..logging_config import log

_SYSTEM_PROMPT: str | None = None


def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is not None:
        return _SYSTEM_PROMPT

    path = Path.cwd() / "sys-prompt.txt"
    try:
        _SYSTEM_PROMPT = path.read_text().strip()
    except FileNotFoundError:
        _SYSTEM_PROMPT = ""
    return _SYSTEM_PROMPT


def _add_cache_control(message: dict[str, Any]) -> dict[str, Any]:
    """Wrap every text part with cache_control: {type: 'ephemeral'}."""
    content = message.get("content")

    if isinstance(content, str):
        return {
            **message,
            "content": [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }

    if isinstance(content, list):
        new_parts = []
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and "cache_control" not in part
            ):
                new_parts.append({**part, "cache_control": {"type": "ephemeral"}})
            else:
                new_parts.append(part)
        return {**message, "content": new_parts}

    return message


def transform_messages(
    messages: list[dict[str, Any]], model: str
) -> list[dict[str, Any]]:
    """Inject system prompt and add cache_control to all messages."""
    transformed = [_add_cache_control(m) for m in messages]

    prompt = _load_system_prompt()
    if not prompt:
        return transformed

    sys_idx = next(
        (i for i, m in enumerate(transformed) if m.get("role") == "system"), None
    )

    if sys_idx is not None:
        existing = transformed[sys_idx]
        if isinstance(existing.get("content"), list):
            old_text = "".join(
                p.get("text", "") for p in existing["content"] if isinstance(p, dict)
            )
        else:
            old_text = str(existing.get("content", ""))
        merged = f"{prompt}\n\n---\n\n{old_text}"
        transformed[sys_idx] = {
            **existing,
            "content": [
                {"type": "text", "text": merged, "cache_control": {"type": "ephemeral"}}
            ],
        }
    else:
        transformed.insert(
            0,
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            },
        )

    log.debug("System prompt injected (%d chars)", len(prompt))
    return transformed

"""POST /v1/chat/completions — proxy to DashScope with retry and streaming."""

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import AuthManager
from ..config import DEFAULT_MODEL, MAX_RETRIES, RETRY_DELAY_S, log
from ..headers import build_headers
from ..models import clamp_max_tokens, resolve_model

router = APIRouter()


async def _handle_regular(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> JSONResponse:
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    return JSONResponse(content=resp.json())


async def _handle_streaming(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> StreamingResponse:
    req = client.build_request("POST", url, json=payload, headers=headers)
    resp = await client.send(req, stream=True)
    resp.raise_for_status()

    async def generate():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> JSONResponse | StreamingResponse:
    from ..main import validate_api_key

    validate_api_key(x_api_key, authorization)

    auth: AuthManager = request.app.state.auth
    client: httpx.AsyncClient = request.app.state.http_client
    request.app.state.request_count += 1

    body: dict[str, Any] = await request.json()
    is_streaming: bool = body.get("stream", False)
    model = resolve_model(body.get("model", DEFAULT_MODEL))
    max_tokens = clamp_max_tokens(model, body.get("max_tokens", 65536))

    access_token = await auth.get_valid_token(client)
    creds = auth.load_credentials()
    url = f"{auth.get_api_endpoint(creds)}/chat/completions"

    payload: dict[str, Any] = {
        "model": model,
        "messages": body.get("messages", []),
        "stream": is_streaming,
        "temperature": body.get("temperature", 0.7),
        "max_tokens": max_tokens,
    }
    for field in (
        "top_p",
        "top_k",
        "repetition_penalty",
        "tools",
        "tool_choice",
        "reasoning",
    ):
        if field in body:
            payload[field] = body[field]

    if is_streaming:
        payload["stream_options"] = {"include_usage": True}

    headers = build_headers(access_token, streaming=is_streaming)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if is_streaming:
                return await _handle_streaming(client, url, payload, headers)
            else:
                return await _handle_regular(client, url, payload, headers)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            if status in (500, 429) and attempt < MAX_RETRIES:
                log.warning("Retry %d/%d (status %d)", attempt, MAX_RETRIES, status)
                await asyncio.sleep(RETRY_DELAY_S * attempt)
                continue
            if status in (400, 401, 403, 504):
                try:
                    log.info("Auth error %d, refreshing token...", status)
                    creds = auth.load_credentials()
                    if creds:
                        new_creds = await auth.refresh_token(creds, client)
                        headers = build_headers(
                            new_creds.access_token, streaming=is_streaming
                        )
                        if is_streaming:
                            return await _handle_streaming(
                                client, url, payload, headers
                            )
                        else:
                            return await _handle_regular(client, url, payload, headers)
                except Exception:
                    pass
            break
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY_S * attempt)
                continue
            break

    error_msg = str(last_error) if last_error else "Unknown error"
    return JSONResponse(
        status_code=500,
        content={"error": {"message": error_msg, "type": "api_error"}},
    )

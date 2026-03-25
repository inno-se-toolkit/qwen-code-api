"""FastAPI application assembly — lifespan, middleware, routers."""

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthManager
from .config import API_KEYS, HOST, PORT, log
from .routes import chat, health, models


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _app.state.auth = AuthManager()
    _app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10))
    _app.state.request_count = 0
    _app.state.start_time = time.time()

    log.info("Server started on %s:%s", HOST, PORT)
    creds = _app.state.auth.load_credentials()
    if creds:
        valid = AuthManager.is_token_valid(creds)
        log.info("Default credentials: %s", "valid" if valid else "expired/invalid")
    else:
        log.warning("No credentials found")

    yield

    await _app.state.http_client.aclose()


app = FastAPI(title="Qwen Code API (Python)", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(chat.router)
app.include_router(models.router)
app.include_router(health.router)


def validate_api_key(
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> None:
    if API_KEYS is None:
        return
    key = x_api_key
    if not key and authorization:
        key = (
            authorization.removeprefix("Bearer ").strip()
            if authorization.startswith("Bearer ")
            else authorization.strip()
        )
    if not key or key not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid or missing API key",
                    "type": "authentication_error",
                }
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)

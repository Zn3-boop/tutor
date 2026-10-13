"""ECV-Tutor — Personalized Tutoring & Adaptive Learning API server.

Clean FastAPI entry point for the Hackathon prototype.
Only mounts: /tutor (core subsystem) + /health (liveness).
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure") and (sys.stderr.encoding or "").lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.api import health, tutor
from app.middleware.rate_limit import rate_limit_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.services.observability.langfuse_client import init_langfuse
        result = init_langfuse()
        if result is not None:
            print("LangFuse initialized (trace will be reported)")
        else:
            print("LangFuse disabled (env vars missing)")
    except Exception as e:
        print(f"LangFuse init skipped: {e}")
    yield

app = FastAPI(
    title="ECV-Tutor",
    description="Personalized Tutoring & Adaptive Learning — Hackathon Prototype",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(rate_limit_middleware)

app.include_router(health.router)
app.include_router(tutor.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Turn unhandled exceptions into a readable JSON 500 instead of a bare
    ``Internal Server Error`` body, and always log the full traceback."""
    import logging
    logging.getLogger(__name__).exception(
        "unhandled error on %s %s", request.method, request.url.path, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"服务器内部错误: {type(exc).__name__}",
            "path": request.url.path,
        },
    )


@app.get("/")
async def root():
    return {"service": "ecv-tutor", "status": "ok", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    # `python -m app.main` — documented in README.md as the canonical way to
    # launch the backend. Without this guard the documented command would
    # import the module and exit silently (causing "500 Internal Server
    # Error" through the Vite dev proxy, which forwards to 127.0.0.1:8000).
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)


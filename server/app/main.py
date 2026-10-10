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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
async def root():
    return {"service": "ecv-tutor", "status": "ok", "docs": "/docs"}


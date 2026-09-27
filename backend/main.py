"""DataWise Backend Application Entry Point.

CRITICAL ARCHITECTURAL CONSTRAINT:
----------------------------------
This application MUST run with a SINGLE WORKER process (workers=1).
The session manager and pipeline state machine rely on an in-process,
isolated session store per decision.md.
Spawning multiple Uvicorn worker processes (--workers > 1) will partition
in-memory session state across isolated OS processes, causing session
lookups and pipeline continuity to fail intermittently.
Do NOT increase worker count without first re-architecting session storage
to an external persistent store (e.g., Redis or PostgreSQL).
"""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.config import ensure_workspace_directories, SESSIONS_DIR
from backend.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to initialize environment on startup."""
    # Ensure local session workspace directory exists on startup
    ensure_workspace_directories()
    yield


app = FastAPI(
    title="DataWise API",
    description="Autonomous AI Data Processing Agent Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes (pipeline, download, session status)
app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for liveness verification."""
    return {"status": "ok"}


if __name__ == "__main__":
    # ENFORCED CONSTRAINT: workers=1 for in-process session stability
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,  # MUST remain 1 for in-process session persistence
    )

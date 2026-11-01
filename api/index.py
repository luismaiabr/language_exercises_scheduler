from datetime import datetime, timezone
import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import scheduler_db
from app.scheduler import scheduler

app = FastAPI(
    title="Language Exercises Email Scheduler",
    description="Automated daily lesson & magic link dispatcher for German micro-lessons",
    version="1.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
@app.get("/", tags=["System"])
def health_check():
    due = scheduler_db.get_due_schedules()
    return {
        "status": "healthy",
        "service": "language_exercises_scheduler",
        "smtp_configured": settings.is_smtp_configured,
        "dry_run": settings.DRY_RUN,
        "frontend_base_url": settings.FRONTEND_BASE_URL,
        "pending_due_lessons": len(due),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.api_route("/api/cron", methods=["GET", "POST"], tags=["Scheduler"])
def run_cron_cycle(authorization: str | None = Header(default=None)):
    """Triggered by Vercel Cron or external scheduler to process due lessons."""
    cron_secret = os.environ.get("CRON_SECRET")
    if cron_secret:
        expected = f"Bearer {cron_secret}"
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Cron Authorization header",
            )

    processed = scheduler.run_once()
    return {
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processed_count": processed,
    }


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from pathlib import Path
import os
import logging

logger = logging.getLogger("gradeflow")

from config import RATE_LIMIT_PER_MINUTE
from database import get_supabase_admin

from routers import auth, courses, dashboard, analytics, students, grading, settings, student, admin

ADMIN_EMAIL = "admin@email.com"
ADMIN_PASSWORD = "admin"
ADMIN_NAME = "System Administrator"


def _seed_admin():
    """Ensure the default admin account exists. Called once at startup."""
    try:
        sb = get_supabase_admin()

        # Check if already exists in profiles
        existing = sb.table("profiles").select("id").eq("role", "admin").limit(1).execute()
        if existing.data:
            logger.info("Admin account already exists — skipping seed.")
            return

        # Create the Supabase auth user
        user_resp = sb.auth.admin.create_user({
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"full_name": ADMIN_NAME, "role": "admin"},
        })

        if not user_resp.user:
            logger.error("Failed to create admin auth user.")
            return

        uid = str(user_resp.user.id)

        # Insert profile
        sb.table("profiles").insert({
            "id": uid,
            "full_name": ADMIN_NAME,
            "role": "admin",
            "department": None,
        }).execute()

        logger.info(f"Admin account created: {ADMIN_EMAIL}")

    except Exception as exc:
        # Non-fatal — server still starts
        logger.warning(f"Admin seed skipped (may already exist): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_admin()
    yield

# ── Rate Limiter ──────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"])

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="GradeFlow API",
    description="Combined LMS Backend — Auth, Instructor, Student, Admin, AI, Career Hub, CollabMesh",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — reads from CORS_ORIGINS env var in production, falls back to localhost for dev
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(students.router)
app.include_router(grading.router)
app.include_router(settings.router)
app.include_router(student.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "GradeFlow API is running 🚀"}

# ── Static file serving (local uploads) ───────────────────────
uploads_dir = Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from core.limiter import limiter

from database import engine
from models import Base, LogLevelEnum, LogCategoryEnum
from api.routers import auth, files, ws, folders, targets, logs, sync
from core.config import settings
from core.logger import log_system_event
from sqlalchemy import text

# ── Ensure storage directories exist ─────────────────────────────────────────
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.THUMBNAILS_DIR, exist_ok=True)
os.makedirs(settings.PREVIEWS_DIR, exist_ok=True)

# ── Create / migrate database tables ─────────────────────────────────────────
Base.metadata.create_all(bind=engine)

try:
    migrations = [
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS date_taken TIMESTAMP;",
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;",
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_path VARCHAR;",
        "ALTER TABLE files ADD COLUMN target_id VARCHAR(36);",
        "ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_base64 VARCHAR;",
        "DROP TABLE IF EXISTS file_data;"
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()
except Exception:
    pass



# ── Auto-Migrate legacy Supabase .env to Targets ─────────────────────────────
try:
    from database import SessionLocal
    from models import User, StorageTarget, ProviderTypeEnum, RoleEnum, File
    from core.security import encrypt_credentials
    
    with SessionLocal() as db_session:
        admin_user = db_session.query(User).filter(User.role == RoleEnum.ADMIN).first()
        if admin_user:
            existing = db_session.query(StorageTarget).filter(StorageTarget.owner_id == admin_user.id).first()
            if not existing and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
                creds = {
                    "supabase_url": settings.SUPABASE_URL,
                    "supabase_key": settings.SUPABASE_SERVICE_KEY,
                    "supabase_bucket": settings.SUPABASE_BUCKET
                }
                encrypted = encrypt_credentials(creds)
                target = StorageTarget(
                    owner_id=admin_user.id,
                    provider_type=ProviderTypeEnum.SUPABASE,
                    connection_name="Default Supabase (Auto-Migrated)",
                    encrypted_credentials=encrypted,
                    is_active=True
                )
                db_session.add(target)
                db_session.commit()
                db_session.refresh(target)
                
                db_session.query(File).update({File.target_id: target.id})
                db_session.commit()
                print("✅ Auto-migrated legacy Supabase config to Target!")
except Exception:
    pass

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.PROJECT_NAME)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Basic CSP - restrict everything to self, allow images from any domain since they come from supabase/cdn
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; media-src 'self' https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline';"
    return response

@app.middleware("http")
async def error_logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            log_system_event(
                level=LogLevelEnum.ERROR,
                category=LogCategoryEnum.SYSTEM,
                message=f"Server error {response.status_code} on {request.method} {request.url.path}"
            )
        elif response.status_code in [401, 403]:
            # Log auth/security failures without spamming too much
            pass
        return response
    except Exception as exc:
        log_system_event(
            level=LogLevelEnum.CRITICAL,
            category=LogCategoryEnum.SYSTEM,
            message=f"Unhandled exception during {request.method} {request.url.path}: {str(exc)}",
            exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        log_system_event(
            level=LogLevelEnum.ERROR,
            category=LogCategoryEnum.SYSTEM,
            message=f"HTTPException {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://frontend-azure-gamma-16.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["sync"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
app.include_router(logs.router,    prefix="/api/v1/logs",    tags=["logs"])
app.include_router(targets.router)
app.include_router(ws.router,      prefix="/api/v1/ws",      tags=["ws"])

# ── Static file serving ───────────────────────────────────────────────────────
app.mount("/uploads",    StaticFiles(directory=settings.UPLOADS_DIR),    name="uploads")
app.mount("/thumbnails", StaticFiles(directory=settings.THUMBNAILS_DIR), name="thumbnails")
app.mount("/previews",   StaticFiles(directory=settings.PREVIEWS_DIR),   name="previews")

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "message": "Media Server is live"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

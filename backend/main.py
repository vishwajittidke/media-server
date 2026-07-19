from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from core.limiter import limiter

from database import engine
from models import Base
from api.routers import auth, files, ws, folders, targets, ai, proxy, config, logs
from core.config import settings
from sqlalchemy import text

# ── Ensure storage directories exist ─────────────────────────────────────────
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.THUMBNAILS_DIR, exist_ok=True)
os.makedirs(settings.PREVIEWS_DIR, exist_ok=True)

# ── Create / migrate database tables ─────────────────────────────────────────
Base.metadata.create_all(bind=engine)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS date_taken TIMESTAMP;"))
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_path VARCHAR;"))
        try:
            conn.execute(text("ALTER TABLE files ADD COLUMN target_id VARCHAR(36);"))
        except Exception:
            pass # Ignore if it exists
        conn.commit()
except Exception as e:
    print(f"Migration note (may already exist): {e}")


# ── Cleanup Ghost Files ──────────────────────────────────────────────────────
# Delete old files that were lost to the ephemeral disk wipe before the FileData fix
try:
    with engine.connect() as conn:
        conn.execute(text("""
            DELETE FROM files 
            WHERE storage_path LIKE '/uploads/%' 
            AND id NOT IN (SELECT file_id FROM file_data)
        """))
        conn.commit()
except Exception as e:
    print(f"Ghost file cleanup failed: {e}")

# NOTE: Render uses ephemeral disks — local files won't exist after a redeploy.
# We now use the database (`file_data` table) to persist files securely.

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
except Exception as e:
    print(f"Auto-migration failed: {e}")

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
app.include_router(auth.router,    prefix="/api/v1/auth",    tags=["auth"])
app.include_router(files.router,   prefix="/api/v1/files",   tags=["files"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
app.include_router(config.router,  prefix="/api/v1/config",  tags=["config"])
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

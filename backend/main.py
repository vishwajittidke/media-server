from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from core.limiter import limiter

from database import engine
from models import Base
from api.routers import auth, files, ws, folders
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
        conn.commit()
except Exception as e:
    print(f"Migration note (may already exist): {e}")

# ── Auto-cleanup orphaned local files on startup ─────────────────────────────
try:
    from database import SessionLocal
    from models import File as DBFile
    with SessionLocal() as db:
        orphaned = db.query(DBFile).filter(~DBFile.storage_path.startswith("http")).all()
        deleted_count = 0
        for f in orphaned:
            local_path = os.path.join(settings.UPLOADS_DIR, f.stored_name)
            if not os.path.exists(local_path):
                db.delete(f)
                deleted_count += 1
        db.commit()
        if deleted_count > 0:
            print(f"🧹 Cleaned up {deleted_count} orphaned local file records (ghost images).")
except Exception as e:
    print(f"Orphan cleanup note: {e}")

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.PROJECT_NAME)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,    prefix="/api/v1/auth",    tags=["auth"])
app.include_router(files.router,   prefix="/api/v1/files",   tags=["files"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
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

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
from api.routers import auth, files, ws, folders
from core.config import settings

# Create database tables
Base.metadata.create_all(bind=engine)

# Auto-migration
# from sqlalchemy import text
# try:
#     with engine.connect() as conn:
#         conn.execute(text("ALTER TABLE files ADD COLUMN is_favorite BOOLEAN DEFAULT FALSE;"))
#         conn.execute(text("ALTER TABLE files ADD COLUMN date_taken TIMESTAMP;"))
#         conn.commit()
# except Exception as e:
#     print(f"Migration failed or already applied: {e}")
# Auto-migration
from sqlalchemy import text
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS date_taken TIMESTAMP;"))
        conn.execute(text("ALTER TABLE files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;"))
        conn.commit()
except Exception as e:
    print(f"Migration failed or already applied: {e}")

app = FastAPI(title=settings.PROJECT_NAME)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Configure CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    settings.FRONTEND_URL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
app.include_router(ws.router, prefix="/api/v1/ws", tags=["ws"])

app.mount("/uploads", StaticFiles(directory="../uploads"), name="uploads")
import os
os.makedirs("../thumbnails", exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory="../thumbnails"), name="thumbnails")
os.makedirs("../previews", exist_ok=True)
app.mount("/previews", StaticFiles(directory="../previews"), name="previews")

@app.get("/api/v1/health")
@app.head("/")
async def root_health_check():
    return {"status": "ok", "message": "Service is live"}
    
async def health_check():
    return {"status": "ok", "message": "Media Server is running"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Media Server API"
    SECRET_KEY: str = "supersecretkeyyoushouldchangeinproduction"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    DATABASE_URL: str = "sqlite:///../database/photodb.sqlite"  # Override with PostgreSQL on Render via env var
    FRONTEND_URL: str = "http://localhost:5173"
    MASTER_ENCRYPTION_KEY: str = ""  # Base64 Fernet key to encrypt credentials

    # Supabase Storage (replaces Cloudinary)
    # Get these from: Supabase Dashboard → Settings → API
    SUPABASE_URL: str = ""          # e.g. https://xyzxyz.supabase.co
    SUPABASE_SERVICE_KEY: str = ""  # "service_role" key (not anon key)
    SUPABASE_BUCKET: str = "media"  # bucket name you create in Supabase Storage

    # Local fallback dirs (only used if Supabase is not configured)
    UPLOADS_DIR: str = "../uploads"
    THUMBNAILS_DIR: str = "../thumbnails"
    PREVIEWS_DIR: str = "../previews"

    class Config:
        env_file = ".env"

settings = Settings()

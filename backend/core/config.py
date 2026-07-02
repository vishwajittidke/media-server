import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Media Server API"
    SECRET_KEY: str = "supersecretkeyyoushouldchangeinproduction"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    DATABASE_URL: str = "sqlite:///../database/photodb.sqlite"
    FRONTEND_URL: str = "http://localhost:5173"
    CLOUDINARY_URL: str = ""
    UPLOADS_DIR: str = "../uploads"
    THUMBNAILS_DIR: str = "../thumbnails"
    PREVIEWS_DIR: str = "../previews"

    class Config:
        env_file = ".env"

settings = Settings()

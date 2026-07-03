from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

kwargs = {"connect_args": connect_args}
if not settings.DATABASE_URL.startswith("sqlite"):
    kwargs["pool_size"] = 5
    kwargs["max_overflow"] = 10
    kwargs["pool_pre_ping"] = True
    kwargs["pool_recycle"] = 300
    kwargs["pool_timeout"] = 30

engine = create_engine(
    settings.DATABASE_URL, **kwargs
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

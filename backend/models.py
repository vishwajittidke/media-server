from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Enum, create_engine, LargeBinary
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
import uuid
import datetime
import enum

Base = declarative_base()

class RoleEnum(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class UploadStatusEnum(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Enum(RoleEnum), default=RoleEnum.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    files = relationship("File", back_populates="owner")
    folders = relationship("Folder", back_populates="owner")

class Folder(Base):
    __tablename__ = "folders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String(36), ForeignKey("folders.id"), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"))
    name = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="folders")
    files = relationship("File", back_populates="folder")
    subfolders = relationship("Folder")

class File(Base):
    __tablename__ = "files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"))
    folder_id = Column(String(36), ForeignKey("folders.id"), nullable=True)
    original_name = Column(String)
    stored_name = Column(String, unique=True)
    extension = Column(String)
    mime_type = Column(String)
    file_size = Column(Integer)
    sha256 = Column(String, index=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    storage_path = Column(String)
    thumbnail_path = Column(String, nullable=True)
    upload_status = Column(Enum(UploadStatusEnum), default=UploadStatusEnum.PENDING)
    is_favorite = Column(Boolean, default=False)
    date_taken = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)  # Recycle Bin: soft-delete timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="files")
    folder = relationship("Folder", back_populates="files")
    tags = relationship("Tag", secondary="file_tags")
    file_data_list = relationship("FileData", back_populates="file", cascade="all, delete-orphan")

class FileData(Base):
    __tablename__ = "file_data"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_id = Column(String(36), ForeignKey("files.id", ondelete="CASCADE"), index=True)
    kind = Column(String)  # "original", "thumbnail", "preview"
    data = Column(LargeBinary)

    file = relationship("File", back_populates="file_data_list")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, index=True)

class FileTag(Base):
    __tablename__ = "file_tags"

    file_id = Column(String(36), ForeignKey("files.id"), primary_key=True)
    tag_id = Column(String(36), ForeignKey("tags.id"), primary_key=True)


from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os
import hashlib
from datetime import datetime
import mimetypes
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import cloudinary
import cloudinary.uploader
import cloudinary.api
from pydantic import BaseModel
import urllib.parse

from core.config import settings
from models import User, File as DBFile, UploadStatusEnum, Folder
from api.deps import get_db, get_current_user
from core.websocket import manager
from core.limiter import limiter

# ── Initialize Cloudinary SDK ───────────────────────────────────────────────
# Cloudinary SDK auto-reads CLOUDINARY_URL if it starts with cloudinary://
# We normalise the URL so both formats work:
#   cloudinary://api_key:api_secret@cloud_name
#   api_key:api_secret@cloud_name  (missing scheme)
if settings.CLOUDINARY_URL:
    url = settings.CLOUDINARY_URL.strip()
    if not url.startswith("cloudinary://"):
        url = "cloudinary://" + url
    try:
        parsed = urllib.parse.urlparse(url)
        cloudinary.config(
            cloud_name=parsed.hostname,
            api_key=parsed.username,
            api_secret=parsed.password,
            secure=True,
        )
        print(f"✅ Cloudinary configured: cloud={parsed.hostname}")
    except Exception as e:
        print(f"❌ Cloudinary config error: {e}")
else:
    print("⚠️  No CLOUDINARY_URL — uploads will be stored on ephemeral local disk only")

router = APIRouter()


def get_file_hash(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def build_cloudinary_urls(sha256: str):
    """Return (thumbnail_url, preview_url) for a Cloudinary-stored file."""
    public_id = f"media_server/{sha256}"
    thumbnail_url = cloudinary.CloudinaryImage(public_id).build_url(
        secure=True, width=400, crop="limit", fetch_format="webp", quality="auto"
    )
    preview_url = cloudinary.CloudinaryImage(public_id).build_url(
        secure=True, width=1920, crop="limit", fetch_format="webp", quality="auto"
    )
    return thumbnail_url, preview_url


def resolve_file_urls(f: DBFile):
    """Given a DBFile ORM object, return thumbnail_url and preview_url."""
    if f.storage_path and f.storage_path.startswith("http"):
        # File is on Cloudinary – generate transformation URLs (no API call)
        thumbnail_url, preview_url = build_cloudinary_urls(f.sha256)
    else:
        # File is on local disk (ephemeral on Render)
        thumbnail_url = f.thumbnail_path or f"/uploads/{f.stored_name}"
        preview_url = f"/previews/{f.stored_name}"
    return thumbnail_url, preview_url


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_files(
    request: Request,
    files: List[UploadFile] = FastAPIFile(...),
    folder_id: str = Form(None),
    date_taken: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    os.makedirs(settings.THUMBNAILS_DIR, exist_ok=True)
    os.makedirs(settings.PREVIEWS_DIR, exist_ok=True)

    uploaded_files_info = []

    for file in files:
        original_name = file.filename or "unknown"
        _, ext = os.path.splitext(original_name)
        ext = ext.lower()
        mime_type, _ = mimetypes.guess_type(original_name)
        mime_type = mime_type or file.content_type or "application/octet-stream"

        # Validate folder ownership
        if folder_id:
            folder = db.query(Folder).filter(
                Folder.id == folder_id, Folder.owner_id == current_user.id
            ).first()
            if not folder:
                folder_id = None

        # Write to a temp file to hash it
        temp_path = os.path.join(settings.UPLOADS_DIR, f"temp_{original_name}")
        try:
            with open(temp_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            file_hash = get_file_hash(temp_path)
            file_size = os.path.getsize(temp_path)

            # Duplicate check (ignores soft-deleted records)
            existing = db.query(DBFile).filter(
                DBFile.sha256 == file_hash,
                DBFile.owner_id == current_user.id,
                DBFile.deleted_at == None,
            ).first()
            if existing:
                os.remove(temp_path)
                uploaded_files_info.append({"filename": original_name, "status": "duplicate", "id": existing.id})
                continue

            stored_name = f"{file_hash}{ext}"
            final_path = os.path.join(settings.UPLOADS_DIR, stored_name)
            os.rename(temp_path, final_path)

            storage_path = f"/uploads/{stored_name}"
            thumbnail_path = f"/thumbnails/{stored_name}"
            cloudinary_success = False

            # ── Upload to Cloudinary ──────────────────────────────────────
            if settings.CLOUDINARY_URL:
                try:
                    upload_res = cloudinary.uploader.upload(
                        final_path,
                        folder="media_server",
                        resource_type="auto",
                        public_id=file_hash,
                    )
                    storage_path = upload_res["secure_url"]
                    cloudinary_success = True

                    if mime_type.startswith("image/"):
                        thumbnail_path, _ = build_cloudinary_urls(file_hash)

                    # Delete local copy – Render's disk is ephemeral anyway
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass

                    print(f"✅ Cloudinary upload OK: {original_name}")
                except Exception as e:
                    import traceback
                    print(f"❌ Cloudinary upload failed: {e}")
                    traceback.print_exc()

            # ── Local thumbnail + preview (fallback) ──────────────────────
            if not cloudinary_success and mime_type.startswith("image/") and os.path.exists(final_path):
                try:
                    with Image.open(final_path) as img:
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        thumb = img.copy()
                        thumb.thumbnail((400, 400))
                        thumb.save(os.path.join(settings.THUMBNAILS_DIR, stored_name), format="JPEG", quality=85)

                    with Image.open(final_path) as img:
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        img.thumbnail((1920, 1080))
                        img.save(os.path.join(settings.PREVIEWS_DIR, stored_name), format="JPEG", quality=85)
                except Exception as e:
                    print(f"Image processing error: {e}")

            # ── Parse date_taken ──────────────────────────────────────────
            parsed_date = None
            if date_taken:
                try:
                    parsed_date = datetime.fromisoformat(date_taken.replace("Z", "+00:00"))
                except Exception:
                    pass

            # ── Save to DB ────────────────────────────────────────────────
            db_file = DBFile(
                owner_id=current_user.id,
                folder_id=folder_id,
                original_name=original_name,
                stored_name=stored_name,
                extension=ext,
                mime_type=mime_type,
                file_size=file_size,
                sha256=file_hash,
                storage_path=storage_path,
                thumbnail_path=thumbnail_path,
                upload_status=UploadStatusEnum.COMPLETED,
                is_favorite=False,
                date_taken=parsed_date,
                deleted_at=None,
            )
            db.add(db_file)
            db.commit()
            db.refresh(db_file)

            # Notify via WebSocket
            try:
                await manager.broadcast_to_user(
                    current_user.id,
                    {"type": "FILE_UPLOADED", "file": {"id": db_file.id, "original_name": db_file.original_name}},
                )
            except Exception:
                pass

            uploaded_files_info.append({"filename": original_name, "status": "success", "id": db_file.id})

        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            print(f"Upload error for {original_name}: {e}")
            uploaded_files_info.append({"filename": original_name, "status": "error", "detail": str(e)})

    return {"uploaded": uploaded_files_info}


# ── List files ───────────────────────────────────────────────────────────────

@router.get("/")
def list_files(
    folder_id: str = None,
    is_favorite: str = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(DBFile).filter(
        DBFile.owner_id == current_user.id,
        DBFile.deleted_at == None,
    )

    if is_favorite and is_favorite.lower() == "true":
        query = query.filter(DBFile.is_favorite == True)
    elif folder_id:
        query = query.filter(DBFile.folder_id == folder_id)
    else:
        query = query.filter(DBFile.folder_id == None)

    from sqlalchemy.sql.functions import coalesce
    files = (
        query.order_by(coalesce(DBFile.date_taken, DBFile.created_at).desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for f in files:
        thumbnail_url, preview_url = resolve_file_urls(f)
        result.append({
            "id": f.id,
            "original_name": f.original_name,
            "stored_name": f.stored_name,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "date_taken": f.date_taken.isoformat() if f.date_taken else None,
            "is_favorite": f.is_favorite,
            "storage_path": f.storage_path,
            "thumbnail_url": thumbnail_url,
            "preview_url": preview_url,
        })
    return result


# ── Download (original quality) ───────────────────────────────────────────────

@router.get("/download/{file_id}")
def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id, DBFile.owner_id == current_user.id
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # If on Cloudinary, redirect to original URL
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        from fastapi.responses import RedirectResponse
        # Build raw original URL (no transformation) for download
        public_id = f"media_server/{db_file.sha256}"
        orig_url = cloudinary.CloudinaryImage(public_id).build_url(secure=True)
        return RedirectResponse(url=orig_url)

    filepath = os.path.join(settings.UPLOADS_DIR, db_file.stored_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Physical file not found on disk")

    return FileResponse(
        path=filepath,
        filename=db_file.original_name,
        media_type=db_file.mime_type,
    )


# ── Soft Delete (send to Recycle Bin) ────────────────────────────────────────

@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id, DBFile.owner_id == current_user.id
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    db_file.deleted_at = datetime.utcnow()
    db_file.updated_at = datetime.utcnow()
    db.commit()


# ── Move ──────────────────────────────────────────────────────────────────────

class MoveRequest(BaseModel):
    folder_id: str = None

class BulkMoveRequest(BaseModel):
    file_ids: List[str]
    folder_id: str = None

@router.put("/{file_id}/move")
def move_file(
    file_id: str,
    body: MoveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id, DBFile.owner_id == current_user.id
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    db_file.folder_id = body.folder_id
    db_file.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}

@router.put("/bulk/move")
def bulk_move_files(
    body: BulkMoveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(DBFile).filter(
        DBFile.id.in_(body.file_ids),
        DBFile.owner_id == current_user.id,
    ).update(
        {"folder_id": body.folder_id, "updated_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return {"status": "ok"}


# ── Favourite ─────────────────────────────────────────────────────────────────

@router.put("/{file_id}/favorite")
def toggle_favorite(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id, DBFile.owner_id == current_user.id
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    db_file.is_favorite = not db_file.is_favorite
    db_file.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok", "is_favorite": db_file.is_favorite}


# ── Recycle Bin ───────────────────────────────────────────────────────────────

@router.get("/trash/list")
def list_trash(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = (
        db.query(DBFile)
        .filter(DBFile.owner_id == current_user.id, DBFile.deleted_at != None)
        .order_by(DBFile.deleted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for f in files:
        thumbnail_url, preview_url = resolve_file_urls(f)
        result.append({
            "id": f.id,
            "original_name": f.original_name,
            "stored_name": f.stored_name,
            "mime_type": f.mime_type,
            "deleted_at": f.deleted_at.isoformat() if f.deleted_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "storage_path": f.storage_path,
            "thumbnail_url": thumbnail_url,
            "preview_url": preview_url,
        })
    return result


@router.put("/trash/{file_id}/restore")
def restore_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id,
        DBFile.owner_id == current_user.id,
        DBFile.deleted_at != None,
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found in trash")

    db_file.deleted_at = None
    db_file.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.delete("/trash/{file_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanent_delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_file = db.query(DBFile).filter(
        DBFile.id == file_id,
        DBFile.owner_id == current_user.id,
        DBFile.deleted_at != None,
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found in trash")

    # Delete from Cloudinary if stored there
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        try:
            cloudinary.uploader.destroy(f"media_server/{db_file.sha256}")
        except Exception as e:
            print(f"Cloudinary delete failed: {e}")
    else:
        # Delete local file
        local = os.path.join(settings.UPLOADS_DIR, db_file.stored_name)
        if os.path.exists(local):
            try:
                os.remove(local)
            except Exception:
                pass

    db.delete(db_file)
    db.commit()


@router.delete("/trash/empty")
def empty_trash(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trashed = db.query(DBFile).filter(
        DBFile.owner_id == current_user.id, DBFile.deleted_at != None
    ).all()

    for f in trashed:
        if f.storage_path and f.storage_path.startswith("http"):
            try:
                cloudinary.uploader.destroy(f"media_server/{f.sha256}")
            except Exception:
                pass
        else:
            local = os.path.join(settings.UPLOADS_DIR, f.stored_name)
            if os.path.exists(local):
                try:
                    os.remove(local)
                except Exception:
                    pass
        db.delete(f)

    db.commit()
    return {"status": "ok", "deleted_count": len(trashed)}

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import hashlib
import io
import mimetypes
import requests
from datetime import datetime
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
from pydantic import BaseModel

from core.config import settings
from models import User, File as DBFile, UploadStatusEnum, Folder
from api.deps import get_db, get_current_user
from core.websocket import manager
from core.limiter import limiter

router = APIRouter()

# ── Supabase Storage helpers ─────────────────────────────────────────────────

def _sb_headers():
    """Auth headers for Supabase Storage REST API."""
    return {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_KEY,
    }

def _sb_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)

def _sb_upload(object_path: str, data: bytes, content_type: str) -> str:
    """
    Upload bytes to Supabase Storage.
    Returns the public URL of the uploaded file.
    Raises on failure.
    """
    bucket = settings.SUPABASE_BUCKET
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        **_sb_headers(),
        "Content-Type": content_type,
        "x-upsert": "true",   # overwrite if already exists (dedup safe)
    }
    resp = requests.post(url, headers=headers, data=data, timeout=120)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase upload failed {resp.status_code}: {resp.text}")
    # Return the public URL
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"

def _sb_delete(object_path: str):
    """Delete a file from Supabase Storage (best-effort)."""
    bucket = settings.SUPABASE_BUCKET
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    try:
        requests.delete(url, headers=_sb_headers(), timeout=30)
    except Exception as e:
        print(f"Supabase delete failed: {e}")

def _sb_transform_url(object_path: str, width: int, quality: int = 80) -> str:
    """
    Build a Supabase image transformation URL (no extra API calls — CDN-based).
    Resizes the image to the given width and sets quality.
    """
    bucket = settings.SUPABASE_BUCKET
    return (
        f"{settings.SUPABASE_URL}/storage/v1/render/image/public/{bucket}/{object_path}"
        f"?width={width}&quality={quality}&resize=contain"
    )


# ── File hash helper ─────────────────────────────────────────────────────────

def get_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── URL resolution ───────────────────────────────────────────────────────────

def resolve_file_urls(f: DBFile):
    """
    Return (thumbnail_url, preview_url) for a file.
    If stored on Supabase (storage_path starts with http) use transform URLs.
    Otherwise fall back to local static paths.
    """
    if f.storage_path and f.storage_path.startswith("http"):
        object_path = f"photos/{f.sha256}{f.extension}"
        if _sb_configured():
            thumbnail_url = _sb_transform_url(object_path, width=400, quality=70)
            preview_url   = _sb_transform_url(object_path, width=1200, quality=70)
        else:
            thumbnail_url = f.storage_path
            preview_url   = f.storage_path
    else:
        thumbnail_url = f.thumbnail_path or f"/uploads/{f.stored_name}"
        preview_url   = f"/previews/{f.stored_name}"
    return thumbnail_url, preview_url


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_files(
    request: Request,
    files: List[UploadFile] = FastAPIFile(...),
    folder_id: Optional[str] = Form(None),
    date_taken: Optional[str] = Form(None),
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

        try:
            raw_bytes = await file.read()
            file_hash = get_file_hash(raw_bytes)
            file_size = len(raw_bytes)

            # Duplicate check (ignores soft-deleted records)
            existing = db.query(DBFile).filter(
                DBFile.sha256 == file_hash,
                DBFile.owner_id == current_user.id,
                DBFile.deleted_at == None,
            ).first()
            if existing:
                uploaded_files_info.append({"filename": original_name, "status": "duplicate", "id": existing.id})
                continue

            stored_name = f"{file_hash}{ext}"
            object_path = f"photos/{stored_name}"   # path inside Supabase bucket

            storage_path  = f"/uploads/{stored_name}"   # local fallback default
            thumbnail_path = f"/thumbnails/{stored_name}"
            supabase_ok = False

            # ── Upload to Supabase Storage ────────────────────────────────
            if _sb_configured():
                try:
                    storage_path = _sb_upload(object_path, raw_bytes, mime_type)
                    supabase_ok = True

                    if mime_type.startswith("image/"):
                        thumbnail_path = _sb_transform_url(object_path, width=400, quality=70)

                    print(f"✅ Supabase upload OK: {original_name} → {object_path}")
                except Exception as e:
                    import traceback
                    print(f"❌ Supabase upload failed for {original_name}: {e}")
                    traceback.print_exc()

            # ── Local fallback (saves to disk if Supabase not configured) ──
            if not supabase_ok:
                final_path = os.path.join(settings.UPLOADS_DIR, stored_name)
                with open(final_path, "wb") as fout:
                    fout.write(raw_bytes)

                if mime_type.startswith("image/"):
                    try:
                        with Image.open(io.BytesIO(raw_bytes)) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            thumb = img.copy()
                            thumb.thumbnail((400, 400))
                            thumb.save(
                                os.path.join(settings.THUMBNAILS_DIR, stored_name),
                                format="JPEG", quality=85,
                            )
                        with Image.open(io.BytesIO(raw_bytes)) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            img.thumbnail((1920, 1080))
                            img.save(
                                os.path.join(settings.PREVIEWS_DIR, stored_name),
                                format="JPEG", quality=85,
                            )
                    except Exception as e:
                        print(f"Local thumbnail error: {e}")

            # ── Parse date_taken ──────────────────────────────────────────
            parsed_date = None
            if date_taken:
                try:
                    parsed_date = datetime.fromisoformat(date_taken.replace("Z", "+00:00"))
                except Exception:
                    pass

            # ── Save record to database ───────────────────────────────────
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

            # Notify connected clients via WebSocket
            try:
                await manager.broadcast_to_user(
                    current_user.id,
                    {"type": "FILE_UPLOADED", "file": {"id": db_file.id, "original_name": db_file.original_name}},
                )
            except Exception:
                pass

            uploaded_files_info.append({"filename": original_name, "status": "success", "id": db_file.id})

        except Exception as e:
            import traceback
            traceback.print_exc()
            uploaded_files_info.append({"filename": original_name, "status": "error", "detail": str(e)})

    return {"uploaded": uploaded_files_info}


# ── List files ───────────────────────────────────────────────────────────────

@router.get("/")
def list_files(
    folder_id: Optional[str] = None,
    is_favorite: Optional[str] = None,
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
        query
        .order_by(coalesce(DBFile.date_taken, DBFile.created_at).desc())
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


# ── Download original quality ────────────────────────────────────────────────

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

    # If stored on Supabase, redirect to the original public URL
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        return RedirectResponse(url=db_file.storage_path)

    # Local fallback
    filepath = os.path.join(settings.UPLOADS_DIR, db_file.stored_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Physical file not found on disk")

    return FileResponse(
        path=filepath,
        filename=db_file.original_name,
        media_type=db_file.mime_type,
    )


# ── Soft delete (Recycle Bin) ────────────────────────────────────────────────

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


# ── Move ─────────────────────────────────────────────────────────────────────

class MoveRequest(BaseModel):
    folder_id: Optional[str] = None

class BulkMoveRequest(BaseModel):
    file_ids: List[str]
    folder_id: Optional[str] = None

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


# ── Favourite ────────────────────────────────────────────────────────────────

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


# ── Recycle Bin ──────────────────────────────────────────────────────────────

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

    # Delete from Supabase Storage
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        object_path = f"photos/{db_file.stored_name}"
        _sb_delete(object_path)
    else:
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
            _sb_delete(f"photos/{f.stored_name}")
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

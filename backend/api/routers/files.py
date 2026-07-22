from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import hashlib
import io
import mimetypes
import base64
import requests
from datetime import datetime
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
from pydantic import BaseModel

from core.config import settings
from models import User, File as DBFile, Tag, FileTag, UploadStatusEnum, Folder
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
    thumbnail_url = f.thumbnail_path or f"/api/v1/files/thumb/{f.stored_name}"
    preview_url = f"/api/v1/files/preview/{f.stored_name}"
    return thumbnail_url, preview_url


# ── Upload ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_files(
    request: Request,
    files: List[UploadFile] = FastAPIFile(...),
    target_id: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
    date_taken: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    os.makedirs(settings.THUMBNAILS_DIR, exist_ok=True)
    os.makedirs(settings.PREVIEWS_DIR, exist_ok=True)

    uploaded_files_info = []

    # ── Storage limit check ──────────────────────────────────────────────
    from sqlalchemy import func as sa_func
    STORAGE_LIMIT = 150 * 1024 * 1024  # 150 MB
    current_usage = db.query(sa_func.sum(DBFile.file_size)).filter(
        DBFile.owner_id == current_user.id, DBFile.deleted_at == None
    ).scalar() or 0
    storage_full = False

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

            # ── Reject if this file would exceed the storage limit ────────
            if current_usage + file_size > STORAGE_LIMIT:
                storage_full = True
                remaining_mb = max(0, (STORAGE_LIMIT - current_usage)) / (1024 * 1024)
                uploaded_files_info.append({
                    "filename": original_name,
                    "status": "storage_exceeded",
                    "detail": f"Storage limit exceeded. {remaining_mb:.1f} MB remaining."
                })
                continue

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

            storage_path  = f"/api/v1/files/raw/{stored_name}"
            thumbnail_path = f"/api/v1/files/thumb/{stored_name}"
            supabase_ok = False

            # ── 1. Generate Thumbnails (Shared Logic) ─────────────────────────
            thumb_bytes = None
            preview_bytes = None

            if mime_type.startswith("image/"):
                try:
                    with Image.open(io.BytesIO(raw_bytes)) as img:
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        # Thumbnail (Very small, saves bandwidth)
                        thumb = img.copy()
                        thumb.thumbnail((600, 600))
                        t_io = io.BytesIO()
                        thumb.save(t_io, format="JPEG", quality=75)
                        thumb_bytes = t_io.getvalue()
                        
                        # Preview (1080p, moderate quality to save RAM/storage)
                        preview = img.copy()
                        preview.thumbnail((1920, 1080))
                        p_io = io.BytesIO()
                        preview.save(p_io, format="JPEG", quality=75)
                        preview_bytes = p_io.getvalue()
                except Exception as e:
                    print(f"Thumbnail generation error: {e}")

            # ── 2. Upload to Selected Storage Target ──────────────────────────────
            target_ok = False
            
            if target_id:
                from models import StorageTarget
                from core.storage import StorageManager
                from core.security import decrypt_credentials
                
                target = db.query(StorageTarget).filter(
                    StorageTarget.id == target_id, 
                    StorageTarget.owner_id == current_user.id
                ).first()
                
                if target and target.encrypted_credentials:
                    try:
                        creds = decrypt_credentials(target.encrypted_credentials)
                        manager = StorageManager(target.provider_type, creds)
                        
                        storage_path = manager.upload(object_path, raw_bytes, mime_type)
                        
                        target_ok = True
                        print(f"✅ Target upload OK: {original_name} -> {target.provider_type}")
                    except Exception as e:
                        import traceback
                        from core.logger import log_system_event, LogLevelEnum, LogCategoryEnum
                        print(f"❌ Target upload failed for {original_name}: {e}")
                        traceback.print_exc()
                        log_system_event(
                            level=LogLevelEnum.ERROR,
                            category=LogCategoryEnum.UPLOAD,
                            message=f"Target storage upload failed for file '{original_name}' on target '{target.connection_name}': {str(e)}",
                            user_id=current_user.id,
                            exc_info=e,
                            db=db
                        )
                        raise HTTPException(status_code=400, detail=f"Target storage upload failed: {str(e)}")

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
                target_id=target_id,
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
                thumbnail_base64="data:image/jpeg;base64," + base64.b64encode(thumb_bytes).decode('utf-8') if thumb_bytes else None
            )
            db.add(db_file)
            db.flush()

            # ── 3. Local fallback & Caching ───────────────────────────────────────
            if not target_ok:
                try:
                    with open(os.path.join(settings.UPLOADS_DIR, stored_name), "wb") as fout:
                        fout.write(raw_bytes)
                except Exception as e:
                    print(f"Cache write error (original): {e}")

            # Always save thumbnails & previews to local DB/Disk for instant loading
            if thumb_bytes:
                try:
                    with open(os.path.join(settings.THUMBNAILS_DIR, stored_name), "wb") as fout:
                        fout.write(thumb_bytes)
                except Exception as e:
                    pass

            if preview_bytes:
                try:
                    with open(os.path.join(settings.PREVIEWS_DIR, stored_name), "wb") as fout:
                        fout.write(preview_bytes)
                except Exception as e:
                    pass

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
            current_usage += file_size

        except Exception as e:
            import traceback
            traceback.print_exc()
            uploaded_files_info.append({"filename": original_name, "status": "error", "detail": str(e)})

    return {"uploaded": uploaded_files_info, "storage_full": storage_full}


# ── List files ───────────────────────────────────────────────────────────────

@router.get("/storage")
def get_storage_usage(target_id: Optional[str] = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy import func
    base_filter = (DBFile.owner_id == current_user.id) & (DBFile.deleted_at == None)
    
    if target_id and target_id != "local":
        base_filter = base_filter & (DBFile.target_id == target_id)
    elif target_id == "local":
        base_filter = base_filter & (DBFile.target_id == None)
        
    used = db.query(func.sum(DBFile.file_size)).filter(base_filter).scalar()
    file_count = db.query(func.count(DBFile.id)).filter(base_filter).scalar()
    
    from core.storage import StorageManager
    from core.security import decrypt_credentials
    
    breakdown = []
    
    # 1. Local Storage
    local_used = db.query(func.sum(DBFile.file_size)).filter(DBFile.owner_id == current_user.id, DBFile.deleted_at == None, DBFile.target_id == None).scalar() or 0
    breakdown.append({
        "provider_type": "LOCAL",
        "connection_name": "Local Storage",
        "used": local_used,
        "limit": 150 * 1024 * 1024,
        "is_configured": True
    })

    from models import StorageTarget, ProviderTypeEnum
    all_targets = db.query(StorageTarget).filter(StorageTarget.owner_id == current_user.id).all()
    configured_types = set()

    # 2. Configured Targets
    for t in all_targets:
        # Default local tracker usage/limit if live fetch fails or is unsupported
        t_used = db.query(func.sum(DBFile.file_size)).filter(DBFile.owner_id == current_user.id, DBFile.deleted_at == None, DBFile.target_id == t.id).scalar() or 0
        t_limit = 0
        if t.provider_type == ProviderTypeEnum.AWS_S3: t_limit = 5 * 1024 * 1024 * 1024
        elif t.provider_type == ProviderTypeEnum.SUPABASE: t_limit = 1 * 1024 * 1024 * 1024
        elif t.provider_type == ProviderTypeEnum.GOOGLE_DRIVE: t_limit = 15 * 1024 * 1024 * 1024
        elif t.provider_type == ProviderTypeEnum.CLOUDINARY: t_limit = 25 * 1024 * 1024 * 1024
        
        # Try live API fetch
        try:
            if t.encrypted_credentials:
                creds = decrypt_credentials(t.encrypted_credentials)
                manager = StorageManager(t.provider_type, creds)
                live_stats = manager.get_storage_stats()
                if live_stats:
                    t_used = live_stats["used"]
                    t_limit = live_stats["limit"]
        except Exception:
            pass

        configured_types.add(t.provider_type.name)
        breakdown.append({
            "id": t.id,
            "provider_type": t.provider_type.name,
            "connection_name": t.connection_name,
            "used": t_used,
            "limit": t_limit,
            "is_configured": True
        })

    # 3. Unconfigured Targets
    unconfigured_defaults = [
        ("AWS_S3", "AWS S3", 5 * 1024 * 1024 * 1024),
        ("SUPABASE", "Supabase", 1 * 1024 * 1024 * 1024),
        ("GOOGLE_DRIVE", "Google Drive", 15 * 1024 * 1024 * 1024),
        ("CLOUDINARY", "Cloudinary", 25 * 1024 * 1024 * 1024)
    ]
    
    for p_type, name, p_limit in unconfigured_defaults:
        if p_type not in configured_types:
            breakdown.append({
                "id": None,
                "provider_type": p_type,
                "connection_name": name,
                "used": 0,
                "limit": p_limit,
                "is_configured": False
            })

    # Recalculate totals based on live stats breakdown to keep it consistent
    if target_id and target_id != "local":
        target_stat = next((b for b in breakdown if b.get("id") == target_id), None)
        if target_stat:
            used = target_stat["used"]
            limit = target_stat["limit"]
    elif not target_id:
        used = sum(b["used"] for b in breakdown if b["is_configured"])
        limit = sum(b["limit"] for b in breakdown if b["is_configured"])

    return {"used": used or 0, "limit": limit, "file_count": file_count or 0, "breakdown": breakdown}

@router.get("/admin/stats")
def get_admin_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role.value != "ADMIN":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin only")
    from sqlalchemy import func
    stats = db.query(
        User.username, 
        func.count(DBFile.id).label('file_count'),
        func.sum(DBFile.file_size).label('total_size')
    ).outerjoin(DBFile, DBFile.owner_id == User.id).group_by(User.username).all()
    
    return [
        {
            "username": row[0],
            "file_count": row[1] or 0,
            "total_size_mb": round((row[2] or 0) / (1024 * 1024), 2)
        }
        for row in stats
    ]

@router.get("/")
def list_files(
    folder_id: Optional[str] = None,
    target_id: Optional[str] = None,
    is_favorite: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(DBFile, User.username).join(User, DBFile.owner_id == User.id).filter(
        DBFile.deleted_at == None
    )

    if current_user.role.value != "ADMIN":
        query = query.filter(DBFile.owner_id == current_user.id)

    if folder_id == "root":
        query = query.filter(DBFile.folder_id == None)
    elif folder_id:
        query = query.filter(DBFile.folder_id == folder_id)
        
    if target_id:
        query = query.filter(DBFile.target_id == target_id)

    if search:
        query = query.filter(DBFile.original_name.ilike(f"%{search}%"))
    elif is_favorite and is_favorite.lower() == "true":
        query = query.filter(DBFile.is_favorite == True)

    from sqlalchemy.sql.functions import coalesce
    files = (
        query
        .order_by(coalesce(DBFile.date_taken, DBFile.created_at).desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for f, owner_username in files:
        thumbnail_url, preview_url = resolve_file_urls(f)
        
        # Safe Base64 Bundle
        thumb_base64 = None
        if f.thumbnail_base64:
            thumb_base64 = f.thumbnail_base64
            
        result.append({
            "id": f.id,
            "original_name": f.original_name,
            "stored_name": f.stored_name,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "date_taken": f.date_taken.isoformat() if f.date_taken else None,
            "is_favorite": f.is_favorite,
            "storage_path": f"/api/v1/files/raw/{f.stored_name}",
            "thumbnail_url": thumbnail_url,
            "preview_url": preview_url,
            "thumbnail_base64": thumb_base64,
            "owner_username": owner_username,
        })
    return result


# ── Download original quality ────────────────────────────────────────────────

@router.get("/download/{file_id}")
@router.get("/{file_id}/download")
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

    # If stored on Supabase, try to proxy the file stream
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"}
        try:
            r = requests.get(db_file.storage_path, headers=headers, stream=True, timeout=10)
            if r.status_code == 200:
                def iterfile():
                    try:
                        for chunk in r.iter_content(chunk_size=8192):
                            yield chunk
                    finally:
                        r.close()
                return StreamingResponse(
                    iterfile(),
                    media_type=db_file.mime_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="{db_file.original_name}"',
                        "Access-Control-Expose-Headers": "Content-Disposition"
                    }
                )
            else:
                r.close()
                # Supabase returned 404 or 403, fallback to DB
                pass
        except Exception as e:
            # Network error connecting to Supabase, fallback to DB
            pass

    # Local fallback: Use the smart serve_file logic which handles DB recovery
    return serve_file(db_file.stored_name, "original", settings.UPLOADS_DIR, db)


# ── Serve Files (Database/Cache Hybrid) ──────────────────────────────────────

def serve_file(stored_name: str, kind: str, cache_dir: str, db: Session):
    # 1. Try local disk cache first
    local_path = os.path.join(cache_dir, stored_name)
    if os.path.exists(local_path):
        return FileResponse(local_path)
    
    # 2. If not in cache (e.g. after Render restart), pull from Database
    db_file = db.query(DBFile).filter(DBFile.stored_name == stored_name).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    # We no longer store LargeBinary in DB. So we MUST proxy from cloud storage if local cache misses.
    if db_file.storage_path and db_file.storage_path.startswith("http"):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(db_file.storage_path, headers=headers, stream=True, timeout=15)
            if r.status_code == 200:
                def iterfile():
                    try:
                        for chunk in r.iter_content(chunk_size=64 * 1024):
                            yield chunk
                    finally:
                        r.close()
                return StreamingResponse(iterfile(), media_type=db_file.mime_type or "image/jpeg")
            else:
                r.close()
        except Exception as e:
            print(f"Proxy stream failed for {db_file.stored_name}: {e}")

        # Fallback for private buckets (403 Forbidden) or other HTTP errors
        if db_file.target_id:
            from models import StorageTarget
            from core.storage import StorageManager
            from core.security import decrypt_credentials
            target = db.query(StorageTarget).filter(StorageTarget.id == db_file.target_id).first()
            if target:
                creds = decrypt_credentials(target.credentials)
                manager = StorageManager(target.provider_type, creds)
                object_path = None
                
                if target.provider_type.name == "AWS_S3" and ".amazonaws.com/" in db_file.storage_path:
                    object_path = db_file.storage_path.split(".amazonaws.com/")[1]
                elif target.provider_type.name == "SUPABASE":
                    bucket = creds.get('supabase_bucket', '')
                    if f"/public/{bucket}/" in db_file.storage_path:
                        object_path = db_file.storage_path.split(f"/public/{bucket}/")[1]
                elif target.provider_type.name == "CLOUDINARY" and "/upload/" in db_file.storage_path:
                    # e.g. https://res.cloudinary.com/demo/image/upload/v1234/sample.jpg
                    parts = db_file.storage_path.split("/")
                    object_path = parts[-1] # fallback filename
                elif target.provider_type.name == "GOOGLE_DRIVE":
                    # e.g. https://drive.google.com/file/d/1A2B3C4D5E/view?usp=drivesdk
                    import re
                    match = re.search(r'/d/([a-zA-Z0-9_-]+)', db_file.storage_path)
                    if match:
                        object_path = match.group(1)
                
                if object_path:
                    try:
                        raw_bytes = manager.download_file(object_path)
                        if raw_bytes:
                            import io
                            return StreamingResponse(io.BytesIO(raw_bytes), media_type=db_file.mime_type or "image/jpeg")
                        else:
                            return Response(content=f"Download returned empty bytes for {object_path}", status_code=500)
                    except Exception as e:
                        return Response(content=f"manager.download_file exception: {e}", status_code=500)
                else:
                    return Response(content=f"object_path is None. storage_path={db_file.storage_path}, provider={target.provider_type.name}", status_code=500)
            else:
                return Response(content=f"Target {db_file.target_id} not found", status_code=500)
            
    # If no URL exists and it's not on disk, it's lost (because we removed FileData).
    raise HTTPException(status_code=404, detail="File data not found")

@router.get("/raw/{stored_name}")
def get_raw_file(stored_name: str, db: Session = Depends(get_db)):
    return serve_file(stored_name, "original", settings.UPLOADS_DIR, db)

@router.get("/thumb/{stored_name}")
def get_thumb_file(stored_name: str, db: Session = Depends(get_db)):
    return serve_file(stored_name, "thumbnail", settings.THUMBNAILS_DIR, db)

@router.get("/preview/{stored_name}")
def get_preview_file(stored_name: str, db: Session = Depends(get_db)):
    return serve_file(stored_name, "preview", settings.PREVIEWS_DIR, db)


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
            "storage_path": f"/api/v1/files/raw/{f.stored_name}",
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


# ── Cleanup orphaned files (old local-path records) ──────────────────────────

@router.delete("/cleanup/orphaned")
def cleanup_orphaned_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove DB records for files that were stored on local disk (not Supabase)
    and whose local files no longer exist (Render wiped them).
    This cleans up the camera-icon ghost entries.
    """
    orphaned = db.query(DBFile).filter(
        DBFile.owner_id == current_user.id,
        ~DBFile.storage_path.startswith("http"),  # local path, not Supabase
    ).all()

    deleted_count = 0
    for f in orphaned:
        local_path = os.path.join(settings.UPLOADS_DIR, f.stored_name)
        if not os.path.exists(local_path):
            db.delete(f)
            deleted_count += 1

    db.commit()
    return {
        "status": "ok",
        "orphaned_found": len(orphaned),
        "deleted": deleted_count,
        "message": f"Removed {deleted_count} orphaned file records. Please re-upload these photos.",
    }

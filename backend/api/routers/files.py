from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import hashlib
from datetime import datetime
import mimetypes
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # Disable decompression bomb limit for huge files
import cloudinary
import cloudinary.uploader
import cloudinary.api
from pydantic import BaseModel

from core.config import settings
from models import User, File as DBFile, UploadStatusEnum, Folder
from api.deps import get_db, get_current_user
from core.websocket import manager
from core.limiter import limiter
import json

router = APIRouter()

def get_file_hash(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@router.post("/", status_code=201)
@limiter.limit("20/minute")
async def upload_files(
    request: Request,
    files: List[UploadFile] = FastAPIFile(...),
    folder_id: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    uploaded_files_info = []

    for file in files:
        # Validate folder if provided
        if folder_id:
            folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user.id).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found or unauthorized")

        # Generate unique storage name
        extension = os.path.splitext(file.filename)[1]
        original_name = file.filename
        
        # Temp save for hashing
        temp_path = os.path.join(settings.UPLOADS_DIR, f"temp_{current_user.id}_{original_name}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_hash = get_file_hash(temp_path)
        file_size = os.path.getsize(temp_path)
        mime_type, _ = mimetypes.guess_type(original_name)
        mime_type = mime_type or "application/octet-stream"

        # Check for duplicates using sha256
        existing_file = db.query(DBFile).filter(DBFile.sha256 == file_hash, DBFile.owner_id == current_user.id).first()
        if existing_file:
            os.remove(temp_path)
            uploaded_files_info.append({"filename": original_name, "status": "duplicate", "id": existing_file.id})
            continue

        stored_name = f"{file_hash}{extension}"
        final_path = os.path.join(settings.UPLOADS_DIR, stored_name)
        
        # Move to final destination locally first
        if not os.path.exists(final_path):
            os.rename(temp_path, final_path)
        else:
            os.remove(temp_path)

        thumbnail_url = None
        preview_url = None

        cloudinary_success = False
        if settings.CLOUDINARY_URL:
            # Upload to Cloudinary
            try:
                upload_res = cloudinary.uploader.upload(
                    final_path, 
                    folder="media_server", 
                    resource_type="auto",
                    public_id=file_hash
                )
                final_path = upload_res.get("secure_url")
                cloudinary_success = True
                
                # Cloudinary automatic transformations
                if mime_type.startswith("image/"):
                    preview_url = cloudinary.CloudinaryImage(upload_res["public_id"]).build_url(
                        secure=True, width=2048, crop="limit", fetch_format="webp", quality="auto"
                    )
                    thumbnail_url = cloudinary.CloudinaryImage(upload_res["public_id"]).build_url(
                        secure=True, width=400, crop="limit", fetch_format="webp", quality="auto"
                    )
            except Exception as e:
                print(f"Cloudinary upload failed: {e}")
                
        if not cloudinary_success:
            # Fallback local generation
            if mime_type.startswith("image/"):
                os.makedirs(settings.THUMBNAILS_DIR, exist_ok=True)
                os.makedirs(settings.PREVIEWS_DIR, exist_ok=True)
                thumb_path = os.path.join(settings.THUMBNAILS_DIR, stored_name)
                preview_path = os.path.join(settings.PREVIEWS_DIR, stored_name)
                
                if not os.path.exists(thumb_path) or not os.path.exists(preview_path):
                    try:
                        with Image.open(final_path) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            preview_img = img.copy()
                            preview_img.thumbnail((2048, 2048))
                            preview_img.save(preview_path, format="JPEG", quality=85)
                            img.thumbnail((400, 400))
                            img.save(thumb_path, format="JPEG", quality=85)
                    except Exception as e:
                        print(f"Image processing failed: {e}")

        # Database record
        db_file = DBFile(
            owner_id=current_user.id,
            folder_id=folder_id,
            original_name=original_name,
            stored_name=stored_name,
            extension=extension,
            mime_type=mime_type,
            file_size=file_size,
            sha256=file_hash,
            storage_path=final_path,
            upload_status=UploadStatusEnum.COMPLETED
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        
        # Broadcast via websocket
        await manager.broadcast(json.dumps({
            "type": "FILE_UPLOADED",
            "file": {
                "id": db_file.id,
                "original_name": db_file.original_name,
                "created_at": str(db_file.created_at)
            }
        }))

        uploaded_files_info.append({"filename": original_name, "status": "success", "id": db_file.id})

    return {"uploaded": uploaded_files_info}

@router.get("/")
def list_files(
    folder_id: str = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(DBFile).filter(DBFile.owner_id == current_user.id)
    if folder_id:
        query = query.filter(DBFile.folder_id == folder_id)
    else:
        query = query.filter(DBFile.folder_id == None)
        
    files = query.order_by(DBFile.created_at.desc()).offset(skip).limit(limit).all()
    
    # Map dynamic URLs if stored on Cloudinary
    result = []
    for f in files:
        f_dict = {
            "id": f.id,
            "original_name": f.original_name,
            "stored_name": f.stored_name,
            "mime_type": f.mime_type,
            "storage_path": f.storage_path
        }
        if f.storage_path and f.storage_path.startswith("http"):
            # It's cloudinary
            public_id = f"media_server/{f.sha256}"
            f_dict["thumbnail_url"] = cloudinary.CloudinaryImage(public_id).build_url(secure=True, width=400, crop="limit", fetch_format="webp", quality="auto")
            f_dict["preview_url"] = cloudinary.CloudinaryImage(public_id).build_url(secure=True, width=2048, crop="limit", fetch_format="webp", quality="auto")
        result.append(f_dict)
        
    return result

@router.get("/download/{file_id}")
def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_file = db.query(DBFile).filter(DBFile.id == file_id, DBFile.owner_id == current_user.id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    if db_file.storage_path.startswith("http"):
        # Redirect to Cloudinary URL for direct download
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=db_file.storage_path)
        
    return FileResponse(
        path=db_file.storage_path,
        filename=db_file.original_name,
        media_type=db_file.mime_type
    )

@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_file = db.query(DBFile).filter(DBFile.id == file_id, DBFile.owner_id == current_user.id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    # Delete from Cloudinary if applicable
    if db_file.storage_path.startswith("http"):
        try:
            cloudinary.uploader.destroy(f"media_server/{db_file.sha256}")
        except Exception as e:
            print(f"Failed to delete from Cloudinary: {e}")
    else:
        # Delete local files
        try:
            if os.path.exists(db_file.storage_path):
                os.remove(db_file.storage_path)
            
            thumb_path = os.path.join(settings.THUMBNAILS_DIR, db_file.stored_name)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                
            preview_path = os.path.join(settings.PREVIEWS_DIR, db_file.stored_name)
            if os.path.exists(preview_path):
                os.remove(preview_path)
        except Exception as e:
            print(f"Failed to delete local files: {e}")

    # Delete from DB
    db.delete(db_file)
    db.commit()
    
    return None

class MoveFileRequest(BaseModel):
    folder_id: str | None = None

@router.put("/{file_id}/move")
def move_file(
    file_id: str,
    request: MoveFileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_file = db.query(DBFile).filter(DBFile.id == file_id, DBFile.owner_id == current_user.id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    if request.folder_id:
        from models import Folder
        folder = db.query(Folder).filter(Folder.id == request.folder_id, Folder.owner_id == current_user.id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Target folder not found")
            
    db_file.folder_id = request.folder_id
    db.commit()
    return {"status": "ok"}

class BulkMoveRequest(BaseModel):
    file_ids: list[str]
    folder_id: str | None = None

@router.put("/bulk/move")
def bulk_move_files(
    request: BulkMoveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if request.folder_id:
        from models import Folder
        folder = db.query(Folder).filter(Folder.id == request.folder_id, Folder.owner_id == current_user.id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Target folder not found")
            
    db.query(DBFile).filter(DBFile.id.in_(request.file_ids), DBFile.owner_id == current_user.id).update(
        {DBFile.folder_id: request.folder_id}, synchronize_session=False
    )
    db.commit()
    return {"status": "ok"}

import base64
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func, func
from typing import Optional

from models import User, File as DBFile, Folder, FileData
from api.deps import get_db, get_current_user
from api.routers.files import resolve_file_urls
from pydantic import BaseModel

router = APIRouter()

class SyncRequest(BaseModel):
    skip: int = 0
    limit: int = 50
    target_id: Optional[str] = None
    folder_id: Optional[str] = None
    is_favorite: Optional[str] = None
    search: Optional[str] = None

@router.post("/")
def sync_data(
    req: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Get Storage Usage
    base_filter = (DBFile.owner_id == current_user.id) & (DBFile.deleted_at == None)
    if req.target_id and req.target_id != "local":
        base_filter = base_filter & (DBFile.target_id == req.target_id)
    elif req.target_id == "local":
        base_filter = base_filter & (DBFile.target_id == None)
        
    used = db.query(func.sum(DBFile.file_size)).filter(base_filter).scalar() or 0
    file_count = db.query(func.count(DBFile.id)).filter(base_filter).scalar() or 0
    storage = {"used": used, "limit": 150 * 1024 * 1024, "file_count": file_count}
    
    # 2. Get Folders
    folders = db.query(Folder).filter(Folder.owner_id == current_user.id).all()
    folder_list = [{"id": f.id, "name": f.name} for f in folders]
    
    # 3. Get Files with Base64 Thumbnails
    query = db.query(DBFile).filter(DBFile.deleted_at == None, DBFile.owner_id == current_user.id)
    if req.folder_id == "root":
        query = query.filter(DBFile.folder_id == None)
    elif req.folder_id:
        query = query.filter(DBFile.folder_id == req.folder_id)
    if req.target_id:
        query = query.filter(DBFile.target_id == req.target_id)
    if req.search:
        query = query.filter(DBFile.original_name.ilike(f"%{req.search}%"))
    else:
        if req.is_favorite and req.is_favorite.lower() == "true":
            query = query.filter(DBFile.is_favorite == True)
        else:
            query = query.filter(DBFile.folder_id == None)
            
    from sqlalchemy.sql.functions import coalesce
    files = query.order_by(coalesce(DBFile.date_taken, DBFile.created_at).desc()).offset(req.skip).limit(req.limit).all()
    
    file_list = []
    for f in files:
        thumbnail_url, preview_url = resolve_file_urls(f)
        
        # Load Base64 Thumbnail
        thumb_base64 = None
        file_data = db.query(FileData).filter(FileData.file_id == f.id, FileData.kind == "thumbnail").first()
        if file_data and file_data.data:
            thumb_base64 = "data:image/jpeg;base64," + base64.b64encode(file_data.data).decode('utf-8')
            
        file_list.append({
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
            "tags": [tag.name for tag in f.tags]
        })

    return {
        "storage": storage,
        "folders": folder_list,
        "files": file_list
    }

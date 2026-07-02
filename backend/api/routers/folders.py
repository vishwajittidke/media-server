from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from models import Folder, User, File
from api.deps import get_db, get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class FolderCreate(BaseModel):
    name: str
    parent_id: str = None

class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None
    owner_id: str
    created_at: datetime

    class Config:
        from_attributes = True

@router.post("/", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(folder_in: FolderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if folder_in.parent_id:
        parent = db.query(Folder).filter(Folder.id == folder_in.parent_id, Folder.owner_id == current_user.id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
            
    db_folder = Folder(
        name=folder_in.name,
        parent_id=folder_in.parent_id,
        owner_id=current_user.id
    )
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder

@router.get("/")
def list_folders(
    parent_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Folder).filter(Folder.owner_id == current_user.id)
    if parent_id:
        query = query.filter(Folder.parent_id == parent_id)
    else:
        query = query.filter(Folder.parent_id == None)
        
    folders = query.order_by(Folder.created_at.desc()).all()
    
    result = []
    for f in folders:
        cover_url = None
        # Get the latest file in this folder for the cover
        latest_file = db.query(File).filter(File.folder_id == f.id).order_by(File.created_at.desc()).first()
        if latest_file and latest_file.storage_path and latest_file.storage_path.startswith("http"):
            public_id = f"media_server/{latest_file.sha256}"
            import cloudinary
            cover_url = cloudinary.CloudinaryImage(public_id).build_url(secure=True, width=400, crop="limit", fetch_format="webp", quality="auto")
            
        result.append({
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "owner_id": f.owner_id,
            "created_at": f.created_at,
            "cover_url": cover_url
        })
        
    return result

@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Detach files from the folder (move them back to root gallery)
    db.query(File).filter(File.folder_id == folder_id).update({File.folder_id: None})
    
    db.delete(folder)
    db.commit()
    return None

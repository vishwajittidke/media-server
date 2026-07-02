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

@router.get("/", response_model=List[FolderOut])
def list_folders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Folder).filter(Folder.owner_id == current_user.id).order_by(Folder.created_at.desc()).all()

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

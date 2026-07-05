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

# @router.get("/")
# def list_folders(
#     parent_id: str = None,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     query = db.query(Folder).filter(Folder.owner_id == current_user.id)
#     if parent_id:
#         query = query.filter(Folder.parent_id == parent_id)
#     else:
#         query = query.filter(Folder.parent_id == None)
        
#     folders = query.order_by(Folder.created_at.desc()).all()
    
#     result = []
#     for f in folders:
#         cover_url = None
#         # Get the latest file in this folder for the cover
#         latest_file = db.query(File).filter(File.folder_id == f.id).order_by(File.created_at.desc()).first()
#         if latest_file and latest_file.storage_path and latest_file.storage_path.startswith("http"):
#             public_id = f"media_server/{latest_file.sha256}"
#             import cloudinary
#             cover_url = cloudinary.CloudinaryImage(public_id).build_url(secure=True, width=400, crop="limit", fetch_format="webp", quality="auto")
            
#         result.append({
#             "id": f.id,
#             "name": f.name,
#             "parent_id": f.parent_id,
#             "owner_id": f.owner_id,
#             "created_at": f.created_at,
#             "cover_url": cover_url
#         })
        
#     return result

@router.get("/")
def list_folders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Fetch all folders for the user in one query
    folders = db.query(Folder).filter(Folder.owner_id == current_user.id).order_by(Folder.created_at.desc()).all()
    
    if not folders:
        return []

    # 2. Extract folder IDs
    folder_ids = [f.id for f in folders]
    
    # 3. Fetch all files belonging to these folders in ONE query, ordered by creation date
    # (We fetch them all to map the latest one in Python, preventing connection drops)
    from models import File as DBFile
    all_folder_files = db.query(DBFile).filter(
        DBFile.folder_id.in_(folder_ids),
        DBFile.mime_type.like("image/%")
    ).order_by(DBFile.folder_id, DBFile.created_at.desc()).all()

    # 4. Map the latest file to each folder using a dictionary
    latest_by_folder = {}
    for file in all_folder_files:
        if file.folder_id not in latest_by_folder:
            latest_by_folder[file.folder_id] = file

    # 5. Build the final response
    result = []
    for f in folders:
        cover_url = None
        latest_file = latest_by_folder.get(f.id)
        
        if latest_file:
            # Map cover image (using Cloudinary or local path)
            if latest_file.storage_path and latest_file.storage_path.startswith("http"):
                public_id = f"media_server/{latest_file.sha256}"
                import cloudinary
                cover_url = cloudinary.CloudinaryImage(public_id).build_url(
                    secure=True, width=400, crop="limit", fetch_format="webp", quality="auto"
                )
            else:
                cover_url = latest_file.thumbnail_path or latest_file.storage_path

        result.append({
            "id": f.id,
            "name": f.name,
            "created_at": f.created_at.isoformat(),
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

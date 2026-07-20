from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import engine, SessionLocal
from models import User, StorageTarget, ProviderTypeEnum, LogLevelEnum, LogCategoryEnum
from api.routers.auth import get_current_user
from schemas.targets import StorageTargetCreate, StorageTargetUpdate, StorageTargetResponse
from core.security import encrypt_credentials
from core.logger import log_system_event

router = APIRouter(
    prefix="/api/v1/targets",
    tags=["targets"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[StorageTargetResponse])
def get_user_targets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    targets = db.query(StorageTarget).filter(StorageTarget.owner_id == current_user.id).all()
    return targets

@router.post("/", response_model=StorageTargetResponse)
def create_target(target: StorageTargetCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Encrypt the credentials before saving to the database
    encrypted_creds = encrypt_credentials(target.credentials)
    
    new_target = StorageTarget(
        owner_id=current_user.id,
        provider_type=target.provider_type,
        connection_name=target.connection_name,
        encrypted_credentials=encrypted_creds,
        is_active=target.is_active
    )
    db.add(new_target)
    db.commit()
    db.refresh(new_target)
    return new_target

@router.put("/{target_id}", response_model=StorageTargetResponse)
def update_target(target_id: str, target: StorageTargetUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_target = db.query(StorageTarget).filter(StorageTarget.id == target_id, StorageTarget.owner_id == current_user.id).first()
    if not db_target:
        raise HTTPException(status_code=404, detail="Target not found")

    if target.connection_name is not None:
        db_target.connection_name = target.connection_name
    if target.is_active is not None:
        db_target.is_active = target.is_active
    if target.credentials is not None:
        # Fetch old credentials to merge with
        from core.security import decrypt_credentials, encrypt_credentials
        old_creds = {}
        if db_target.encrypted_credentials:
            old_creds = decrypt_credentials(db_target.encrypted_credentials)
            
        # Merge new creds into old creds (only overwrite if new value is not empty)
        for k, v in target.credentials.items():
            if v and str(v).strip() != "":
                old_creds[k] = v
                
        db_target.encrypted_credentials = encrypt_credentials(old_creds)

    db.commit()
    db.refresh(db_target)
    return db_target

@router.delete("/{target_id}")
def delete_target(target_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_target = db.query(StorageTarget).filter(StorageTarget.id == target_id, StorageTarget.owner_id == current_user.id).first()
    if not db_target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    db.delete(db_target)
    db.commit()
    return {"message": "Target deleted successfully"}

from fastapi import BackgroundTasks
import hashlib
from PIL import Image
import io
import mimetypes

from models import File as DBFile, FileData
from core.storage import StorageManager
from core.security import decrypt_credentials

def sync_target_task(target_id: str, owner_id: str):
    db = SessionLocal()
    try:
        db_target = db.query(StorageTarget).filter(StorageTarget.id == target_id, StorageTarget.owner_id == owner_id).first()
        if not db_target or not db_target.is_active:
            return
            
        credentials = decrypt_credentials(db_target.encrypted_credentials)
        manager = StorageManager(provider_type=db_target.provider_type, credentials=credentials)
        
        remote_files = manager.list_files()
        
        # We need to filter out files that are already in the database
        # For simplicity, we check if the storage_path (URL) already exists, or original_name if ID is used
        for remote_file in remote_files:
            try:
                # If name looks like a hash (from Media Server uploads), check by sha256
                assumed_hash = remote_file['name'].split('.')[0]
                if len(assumed_hash) == 64:
                    existing = db.query(DBFile).filter(
                        DBFile.owner_id == owner_id,
                        DBFile.sha256 == assumed_hash
                    ).first()
                    if existing:
                        continue
                else:
                    existing = db.query(DBFile).filter(
                        DBFile.owner_id == owner_id,
                        DBFile.target_id == target_id,
                        DBFile.original_name == remote_file['name']
                    ).first()
                    if existing:
                        continue
                        
                # Download file to generate thumbnail
                raw_bytes = manager.download_file(remote_file['id'])
                if not raw_bytes:
                    continue
                    
                # Generate SHA256
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                
                # Check again by sha256 to prevent IntegrityError on unique constraint
                existing_by_hash = db.query(DBFile).filter(DBFile.owner_id == owner_id, DBFile.sha256 == sha256).first()
                if existing_by_hash:
                    continue
                    
                mime_type = remote_file.get('mime_type') or mimetypes.guess_type(remote_file['name'])[0] or "application/octet-stream"
                stored_name = f"{sha256}.{remote_file['name'].split('.')[-1]}" if '.' in remote_file['name'] else f"{sha256}.jpeg"
                
                # Generate thumbnail
                thumb_bytes = None
                preview_bytes = None
                if mime_type.startswith("image/"):
                    try:
                        with Image.open(io.BytesIO(raw_bytes)) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            
                            thumb = img.copy()
                            thumb.thumbnail((600, 600))
                            t_io = io.BytesIO()
                            thumb.save(t_io, format="JPEG", quality=75)
                            thumb_bytes = t_io.getvalue()
                            
                            prev = img.copy()
                            prev.thumbnail((1920, 1080))
                            p_io = io.BytesIO()
                            prev.save(p_io, format="JPEG", quality=85)
                            preview_bytes = p_io.getvalue()
                    except Exception as e:
                        print(f"Thumbnail generation error during sync: {e}")
                
                thumbnail_path = f"/api/v1/files/thumb/{stored_name}"
                preview_path = f"/api/v1/files/preview/{stored_name}"
                
                db_file = DBFile(
                    owner_id=owner_id,
                    original_name=remote_file['name'],
                    stored_name=stored_name,
                    mime_type=mime_type,
                    size=len(raw_bytes),
                    sha256=sha256,
                    target_id=target_id,
                    storage_path=remote_file['url'],
                    thumbnail_path=thumbnail_path,
                    preview_path=preview_path,
                )
                db.add(db_file)
                db.flush()
                
                if thumb_bytes:
                    db.add(FileData(file_id=db_file.id, kind="thumbnail", data=thumb_bytes))
                if preview_bytes:
                    db.add(FileData(file_id=db_file.id, kind="preview", data=preview_bytes))
                    
                db.commit()
            except Exception as loop_e:
                db.rollback()
                log_system_event(LogLevelEnum.ERROR, LogCategoryEnum.SYNC, f"Error syncing file {remote_file.get('name')}: {loop_e}", user_id=owner_id, db=db)
                
    except Exception as e:
        import traceback
        log_system_event(LogLevelEnum.ERROR, LogCategoryEnum.SYNC, f"Sync target task failed: {e}\n{traceback.format_exc()}", user_id=owner_id, db=db)
    finally:
        db.close()

@router.post("/{target_id}/sync")
def sync_target(target_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_target = db.query(StorageTarget).filter(StorageTarget.id == target_id, StorageTarget.owner_id == current_user.id).first()
    if not db_target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    background_tasks.add_task(sync_target_task, target_id, current_user.id)
    return {"message": "Sync started"}

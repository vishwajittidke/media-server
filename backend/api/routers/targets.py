from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import engine, SessionLocal
from models import User, StorageTarget, ProviderTypeEnum
from api.routers.auth import get_current_user
from schemas.targets import StorageTargetCreate, StorageTargetUpdate, StorageTargetResponse
from core.security import encrypt_credentials

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
        db_target.encrypted_credentials = encrypt_credentials(target.credentials)

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

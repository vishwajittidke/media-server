from pydantic import BaseModel
from typing import Optional, Any, Dict
from models import ProviderTypeEnum
from datetime import datetime

class StorageTargetBase(BaseModel):
    provider_type: ProviderTypeEnum
    connection_name: str
    is_active: bool = True

class StorageTargetCreate(StorageTargetBase):
    credentials: Dict[str, Any]

class StorageTargetUpdate(BaseModel):
    connection_name: Optional[str] = None
    is_active: Optional[bool] = None
    credentials: Optional[Dict[str, Any]] = None

class StorageTargetResponse(StorageTargetBase):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    
    # Notice we DO NOT return the encrypted_credentials in the response for security!
    
    class Config:
        orm_mode = True

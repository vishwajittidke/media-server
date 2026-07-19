from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from api.deps import get_db
from models import User, SystemLog, RoleEnum
from core.security import get_current_user
from schemas.logs import SystemLogResponse

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("/", response_model=List[SystemLogResponse])
def get_system_logs(
    level: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only admins can view logs
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to view system logs")

    query = db.query(SystemLog)
    
    if level:
        query = query.filter(SystemLog.level.ilike(level))
    if category:
        query = query.filter(SystemLog.category.ilike(category))
        
    # Order by newest first
    logs = query.order_by(SystemLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs

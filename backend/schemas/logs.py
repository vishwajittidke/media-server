from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models import LogLevelEnum, LogCategoryEnum

class SystemLogResponse(BaseModel):
    id: str
    level: LogLevelEnum
    category: LogCategoryEnum
    message: str
    stack_trace: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

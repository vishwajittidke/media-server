from pydantic import BaseModel
from typing import Optional
import json

class SyncRequest(BaseModel):
    skip: int = 0
    limit: int = 50
    target_id: Optional[str] = None
    folder_id: Optional[str] = None
    search: Optional[str] = None
    is_favorite: Optional[str] = None

payload = json.loads('{"skip":0,"limit":50}')
req = SyncRequest(**payload)
print(req)

payload = json.loads('{"skip":0,"limit":50, "target_id": null}')
req2 = SyncRequest(**payload)
print(req2)

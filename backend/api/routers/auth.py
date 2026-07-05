from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
import requests as http_requests

from core.security import verify_password, get_password_hash, create_access_token
from core.config import settings
from models import User, RoleEnum, File as DBFile
from schemas.auth import Token, UserCreate, UserOut
from api.deps import get_db, get_current_user
import uuid
from core.limiter import limiter

router = APIRouter()

# Cookie config
COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
COOKIE_SAMESITE = "none"   # Required for cross-origin (Vercel → Render)
COOKIE_SECURE = True       # Required when SameSite=none (HTTPS only)


def _set_auth_cookie(response: JSONResponse, token: str) -> JSONResponse:
    """Set the JWT as an HTTP-only, Secure cookie on the response."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=COOKIE_MAX_AGE,
        path="/",
    )
    return response


@router.post("/login")
@limiter.limit("20/minute")
def login_access_token(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    
    # Return the token in the JSON body (for WebSocket connections that need it)
    # AND set it as an HTTP-only cookie (for all fetch requests)
    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
    })
    _set_auth_cookie(response, access_token)
    return response


@router.post("/logout")
def logout(request: Request):
    """Clear the auth cookie."""
    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )
    return response


@router.get("/check")
def check_session(current_user: User = Depends(get_current_user)):
    """Validate the current session cookie. Returns user info if valid."""
    return {"authenticated": True, "username": current_user.username, "id": current_user.id}


@router.post("/register", response_model=UserOut)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_in.username).first()
    if user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if first user, make them ADMIN
    is_first = db.query(User).count() == 0
    role = RoleEnum.ADMIN if is_first else RoleEnum.USER
    
    user = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.put("/change-password")
def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    
    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()
    return {"status": "success"}

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Fetch all user's files
    user_files = db.query(DBFile).filter(DBFile.owner_id == current_user.id).all()
    
    # 1. Delete from Supabase Storage to prevent orphaned files
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        headers = {
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        }
        for db_file in user_files:
            if db_file.storage_path and db_file.storage_path.startswith("http"):
                try:
                    object_path = f"photos/{db_file.stored_name}"
                    url = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_BUCKET}/{object_path}"
                    http_requests.delete(url, headers=headers, timeout=10)
                except Exception as e:
                    print(f"Failed to delete {db_file.stored_name} from Supabase: {e}")
                
    # 2. Delete from database
    db.query(DBFile).filter(DBFile.owner_id == current_user.id).delete(synchronize_session=False)
    
    # 3. Delete the user
    db.delete(current_user)
    db.commit()
    return None

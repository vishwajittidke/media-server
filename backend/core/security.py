from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
from passlib.context import CryptContext
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

from cryptography.fernet import Fernet
import json

def get_fernet() -> Fernet:
    if not settings.MASTER_ENCRYPTION_KEY:
        import base64
        import hashlib
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key)
        return Fernet(fernet_key)
    return Fernet(settings.MASTER_ENCRYPTION_KEY.encode('utf-8'))

def encrypt_credentials(creds_dict: dict) -> str:
    f = get_fernet()
    json_str = json.dumps(creds_dict)
    return f.encrypt(json_str.encode('utf-8')).decode('utf-8')

def decrypt_credentials(encrypted_str: str) -> dict:
    f = get_fernet()
    json_str = f.decrypt(encrypted_str.encode('utf-8')).decode('utf-8')
    return json.loads(json_str)

def generate_master_key() -> str:
    return Fernet.generate_key().decode('utf-8')

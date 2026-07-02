import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import SessionLocal
from models import User, RoleEnum
from core.security import get_password_hash

def init_admin(username, email, password):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    if user:
        print("Admin user already exists.")
        return
    
    admin_user = User(
        username=username,
        email=email,
        password_hash=get_password_hash(password),
        role=RoleEnum.ADMIN
    )
    db.add(admin_user)
    db.commit()
    print(f"Admin user '{username}' created successfully!")
    db.close()

if __name__ == "__main__":
    init_admin("admin", "admin@example.com", "admin123")

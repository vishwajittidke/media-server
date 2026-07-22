from database import SessionLocal
from models import File as DBFile, User
from sqlalchemy.sql.functions import coalesce

db = SessionLocal()
user = db.query(User).first()

if not user:
    print("No user found")
    exit()

print(f"Testing for user {user.username} (ID: {user.id})")

query = db.query(DBFile).filter(DBFile.deleted_at == None, DBFile.owner_id == user.id)
# Simulate target_id = None
# query = query.filter(DBFile.target_id == None) # We DON'T apply this!

# Simulate folder_id = None (the old else block behavior)
query = query.filter(DBFile.folder_id == None)

files = query.order_by(coalesce(DBFile.date_taken, DBFile.created_at).desc()).all()

print(f"Total files returned: {len(files)}")
for f in files:
    print(f" - {f.original_name} (target_id: {f.target_id})")

# Let's see all files for this user regardless of folder_id
all_files = db.query(DBFile).filter(DBFile.deleted_at == None, DBFile.owner_id == user.id).all()
print(f"Total files in DB for user: {len(all_files)}")

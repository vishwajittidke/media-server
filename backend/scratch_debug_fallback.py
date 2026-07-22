from database import SessionLocal
from models import File as DBFile, StorageTarget
from core.storage import StorageManager
from core.security import decrypt_credentials

db = SessionLocal()
db_file = db.query(DBFile).filter(DBFile.stored_name == "4ef36aae42a63927c07364794c1f2721a1c4ca3ab691fa5d009b46e040ebd201.jpeg").first()

print(f"File found: {db_file is not None}")
if db_file:
    print(f"Target ID: {db_file.target_id}")
    print(f"Storage Path: {db_file.storage_path}")
    
    target = db.query(StorageTarget).filter(StorageTarget.id == db_file.target_id).first()
    print(f"Target found: {target is not None}")
    if target:
        print(f"Provider Type: {target.provider_type.name}")
        creds = decrypt_credentials(target.credentials)
        manager = StorageManager(target.provider_type, creds)
        
        object_path = None
        if target.provider_type.name == "AWS_S3" and ".amazonaws.com/" in db_file.storage_path:
            object_path = db_file.storage_path.split(".amazonaws.com/")[1]
            
        print(f"Parsed Object Path: {object_path}")
        if object_path:
            try:
                raw_bytes = manager.download_file(object_path)
                print(f"Downloaded bytes length: {len(raw_bytes)}")
            except Exception as e:
                print(f"Download error: {e}")

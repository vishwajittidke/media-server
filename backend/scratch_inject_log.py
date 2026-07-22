from database import SessionLocal
from models import SystemLog, LogLevelEnum, LogCategoryEnum

def inject_test_log():
    db = SessionLocal()
    try:
        log = SystemLog(
            level=LogLevelEnum.ERROR,
            category=LogCategoryEnum.UPLOAD,
            message="Test Error: Storage bucket full or permission denied during upload.",
            stack_trace="Traceback (most recent call last):\n  File \"upload.py\", line 45\n    raise StorageError(\"Bucket Full\")\nStorageError: Bucket Full",
            user_id="SYSTEM"
        )
        db.add(log)
        db.commit()
        print("Successfully injected test log!")
    finally:
        db.close()

if __name__ == "__main__":
    inject_test_log()

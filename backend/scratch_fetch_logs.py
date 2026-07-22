from database import SessionLocal
from models import SystemLog
from sqlalchemy import desc

def fetch_logs():
    db = SessionLocal()
    try:
        logs = db.query(SystemLog).order_by(desc(SystemLog.created_at)).limit(5).all()
        if not logs:
            print("No logs found in DB.")
        for log in logs:
            print(f"[{log.level.value}] {log.category.value} - {log.message}")
            if log.stack_trace:
                print(f"TRACE: {log.stack_trace}")
            print("-" * 40)
    finally:
        db.close()

if __name__ == "__main__":
    fetch_logs()

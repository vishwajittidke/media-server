from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Connecting to {DATABASE_URL}")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE files ADD COLUMN thumbnail_base64 VARCHAR;"))
        print("Added thumbnail_base64 to files.")
    except Exception as e:
        print(f"Column already exists or error: {e}")
        
    try:
        conn.execute(text("DROP TABLE file_data;"))
        print("Dropped file_data table.")
    except Exception as e:
        print(f"Table already dropped or error: {e}")

    conn.commit()
    print("Migration complete!")

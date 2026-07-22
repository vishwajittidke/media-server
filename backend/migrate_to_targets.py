import os
import sys

# Add backend dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.security import generate_master_key
from core.config import settings

def main():
    print("==================================================")
    print("Multi-Cloud Target Migration Script")
    print("==================================================")
    
    # 1. Generate Master Key
    print("\n[Step 1] Generating Master Encryption Key...")
    master_key = generate_master_key()
    print("\n*** CRITICAL ACTION REQUIRED ***")
    print(f"Please add the following key to your .env file AND your Render Environment Variables:")
    print(f"MASTER_ENCRYPTION_KEY={master_key}")
    print("****************************************\n")
    
    # 2. Update .env locally for this script to work
    try:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            with open(env_path, 'a') as f:
                f.write(f"\nMASTER_ENCRYPTION_KEY={master_key}\n")
            print("Successfully added MASTER_ENCRYPTION_KEY to local .env")
    except Exception as e:
        print(f"Failed to update local .env automatically: {e}")
    
    # Reload settings directly in this process to use the new key
    os.environ['MASTER_ENCRYPTION_KEY'] = master_key
    settings.MASTER_ENCRYPTION_KEY = master_key

    # 3. Create Default Supabase Target
    print("\n[Step 2] Migrating existing Supabase configuration to a database Target...")
    from database import SessionLocal
    from models import User, StorageTarget, ProviderTypeEnum, RoleEnum
    from core.security import encrypt_credentials

    db = SessionLocal()
    from database import engine
    from models import Base
    Base.metadata.create_all(bind=engine)
    try:
        admin_user = db.query(User).filter(User.role == RoleEnum.ADMIN).first()
        if not admin_user:
            print("No admin user found. Please run this after creating an account.")
            return

        # Check if they already have targets
        existing = db.query(StorageTarget).filter(StorageTarget.owner_id == admin_user.id).first()
        if existing:
            print("Admin user already has storage targets configured. Skipping migration.")
            return

        # Create Supabase target
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
            creds = {
                "supabase_url": settings.SUPABASE_URL,
                "supabase_key": settings.SUPABASE_SERVICE_KEY,
                "supabase_bucket": settings.SUPABASE_BUCKET
            }
            encrypted = encrypt_credentials(creds)
            
            target = StorageTarget(
                owner_id=admin_user.id,
                provider_type=ProviderTypeEnum.SUPABASE,
                connection_name="Default Supabase (Auto-Migrated)",
                encrypted_credentials=encrypted,
                is_active=True
            )
            db.add(target)
            db.commit()
            db.refresh(target)
            
            # Link all existing files to this target
            from models import File
            db.query(File).update({File.target_id: target.id})
            db.commit()
            print(f"Successfully migrated {db.query(File).count()} files to the new Supabase target!")
        else:
            print("No existing Supabase configuration found in .env. Skipping target creation.")
    except Exception as e:
        print(f"Error migrating: {e}")
    finally:
        db.close()

    print("\n==================================================")
    print("Migration complete!")
    print("==================================================")

if __name__ == "__main__":
    main()

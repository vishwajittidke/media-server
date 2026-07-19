import boto3
from botocore.exceptions import ClientError
import cloudinary
import cloudinary.uploader
import requests
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from models import ProviderTypeEnum

class StorageManager:
    def __init__(self, provider_type: ProviderTypeEnum, credentials: dict):
        self.provider_type = provider_type
        self.credentials = credentials
        
    def upload(self, object_path: str, data: bytes, content_type: str) -> str:
        if self.provider_type == ProviderTypeEnum.AWS_S3:
            s3 = boto3.client(
                's3',
                region_name=self.credentials.get('region', 'us-east-1'),
                aws_access_key_id=self.credentials.get('access_key'),
                aws_secret_access_key=self.credentials.get('secret_key')
            )
            bucket = self.credentials.get('bucket')
            s3.put_object(
                Bucket=bucket,
                Key=object_path,
                Body=data,
                ContentType=content_type,
                ACL='public-read'  # Assuming public gallery for now
            )
            region = self.credentials.get('region', 'us-east-1')
            return f"https://{bucket}.s3.{region}.amazonaws.com/{object_path}"
            
        elif self.provider_type == ProviderTypeEnum.CLOUDINARY:
            cloudinary.config(
                cloud_name=self.credentials.get('cloud_name'),
                api_key=self.credentials.get('api_key'),
                api_secret=self.credentials.get('api_secret')
            )
            # Cloudinary usually expects public_id without extension
            public_id = object_path.split('.')[0]
            resp = cloudinary.uploader.upload(
                data,
                public_id=public_id,
                resource_type="auto"
            )
            return resp.get('secure_url')
            
        elif self.provider_type == ProviderTypeEnum.SUPABASE:
            supabase_url = self.credentials.get('supabase_url')
            supabase_key = self.credentials.get('supabase_key')
            bucket = self.credentials.get('supabase_bucket')
            
            url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            }
            resp = requests.post(url, headers=headers, data=data, timeout=120)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Supabase upload failed {resp.status_code}: {resp.text}")
            return f"{supabase_url}/storage/v1/object/public/{bucket}/{object_path}"
            
        elif self.provider_type == ProviderTypeEnum.GOOGLE_DRIVE:
            service_account_info = json.loads(self.credentials.get('service_account_json', '{}'))
            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            drive_service = build('drive', 'v3', credentials=creds)
            
            file_metadata = {'name': object_path.split('/')[-1]}
            media = MediaIoBaseUpload(io.BytesIO(data), mimetype=content_type, resumable=True)
            
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            # Make public
            drive_service.permissions().create(
                fileId=file.get('id'),
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
            
            return file.get('webViewLink')
            
        raise ValueError("Unsupported provider type")

    def delete(self, object_path: str):
        try:
            if self.provider_type == ProviderTypeEnum.AWS_S3:
                s3 = boto3.client(
                    's3',
                    region_name=self.credentials.get('region', 'us-east-1'),
                    aws_access_key_id=self.credentials.get('access_key'),
                    aws_secret_access_key=self.credentials.get('secret_key')
                )
                bucket = self.credentials.get('bucket')
                s3.delete_object(Bucket=bucket, Key=object_path)
                
            elif self.provider_type == ProviderTypeEnum.CLOUDINARY:
                cloudinary.config(
                    cloud_name=self.credentials.get('cloud_name'),
                    api_key=self.credentials.get('api_key'),
                    api_secret=self.credentials.get('api_secret')
                )
                public_id = object_path.split('.')[0]
                cloudinary.uploader.destroy(public_id)
                
            elif self.provider_type == ProviderTypeEnum.SUPABASE:
                supabase_url = self.credentials.get('supabase_url')
                supabase_key = self.credentials.get('supabase_key')
                bucket = self.credentials.get('supabase_bucket')
                url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "apikey": supabase_key,
                }
                requests.delete(url, headers=headers, timeout=30)
                
            elif self.provider_type == ProviderTypeEnum.GOOGLE_DRIVE:
                # Google Drive doesn't use object paths like S3, it uses IDs.
                # A proper implementation would query the ID by name first.
                # For this proof of concept, we skip deletion logic for GD if we don't have the ID saved.
                pass
        except Exception as e:
            print(f"Delete failed for {self.provider_type}: {e}")

    def get_url(self, object_path: str) -> str:
        # Reconstruct URLs (assuming public read is enabled for all integrations)
        if self.provider_type == ProviderTypeEnum.AWS_S3:
            bucket = self.credentials.get('bucket')
            region = self.credentials.get('region', 'us-east-1')
            return f"https://{bucket}.s3.{region}.amazonaws.com/{object_path}"
            
        elif self.provider_type == ProviderTypeEnum.SUPABASE:
            supabase_url = self.credentials.get('supabase_url')
            bucket = self.credentials.get('supabase_bucket')
            return f"{supabase_url}/storage/v1/object/public/{bucket}/{object_path}"
            
        # Cloudinary and Google Drive usually require storing the specific URL 
        # returned from the upload API. For now, we fallback to local proxy if needed.
        return ""

    def get_storage_stats(self) -> dict:
        """
        Dynamically fetches the real storage usage and limit from the provider API.
        Returns {"used": int, "limit": int} or None if the provider doesn't support it.
        """
        try:
            if self.provider_type == ProviderTypeEnum.GOOGLE_DRIVE:
                service_account_info = json.loads(self.credentials.get('service_account_json', '{}'))
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
                drive_service = build('drive', 'v3', credentials=creds)
                about = drive_service.about().get(fields="storageQuota").execute()
                quota = about.get('storageQuota', {})
                return {
                    "used": int(quota.get('usage', 0)),
                    "limit": int(quota.get('limit', 0)) if quota.get('limit') else 15 * 1024 * 1024 * 1024
                }
                
            elif self.provider_type == ProviderTypeEnum.CLOUDINARY:
                cloudinary.config(
                    cloud_name=self.credentials.get('cloud_name'),
                    api_key=self.credentials.get('api_key'),
                    api_secret=self.credentials.get('api_secret')
                )
                import cloudinary.api
                usage = cloudinary.api.usage()
                storage = usage.get('storage', {})
                return {
                    "used": int(storage.get('usage', 0)),
                    "limit": int(storage.get('limit', 25 * 1024 * 1024 * 1024))
                }
                
            # For S3 and Supabase, getting bucket size synchronously is not natively supported 
            # by a simple API call (S3 requires CloudWatch or paginated list, Supabase requires Postgres RPC).
            # We return None so the backend falls back to our local DB tracker.
            return None
        except Exception as e:
            print(f"Failed to fetch live stats for {self.provider_type}: {e}")
            return None

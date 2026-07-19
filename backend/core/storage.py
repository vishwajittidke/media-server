import boto3
from botocore.exceptions import ClientError
import cloudinary
import cloudinary.uploader
import requests
import io
import json
from google.oauth2 import service_account, credentials as google_credentials
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
            # Try OAuth2 Refresh Token first (avoids quota issues)
            if self.credentials.get('refresh_token'):
                creds = google_credentials.Credentials(
                    token=None,
                    refresh_token=self.credentials.get('refresh_token'),
                    client_id=self.credentials.get('client_id'),
                    client_secret=self.credentials.get('client_secret'),
                    token_uri='https://oauth2.googleapis.com/token',
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            else:
                # Fallback to Service Account (requires Workspace Shared Drive to avoid quota error)
                service_account_info = json.loads(self.credentials.get('service_account_json', '{}'))
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            drive_service = build('drive', 'v3', credentials=creds)
            
            file_metadata = {'name': object_path.split('/')[-1]}
            folder_id = self.credentials.get('folder_id')
            if folder_id:
                file_metadata['parents'] = [folder_id]
                
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
                if self.credentials.get('refresh_token'):
                    creds = google_credentials.Credentials(
                        token=None,
                        refresh_token=self.credentials.get('refresh_token'),
                        client_id=self.credentials.get('client_id'),
                        client_secret=self.credentials.get('client_secret'),
                        token_uri='https://oauth2.googleapis.com/token',
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                else:
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
                    "limit": int(quota.get('limit', 0)) if int(quota.get('limit', 0)) > 0 else 15 * 1024 * 1024 * 1024
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

    def list_files(self) -> list:
        """
        List files in the target storage.
        Returns a list of dictionaries with 'name', 'id' (or path), and 'url' (if available).
        """
        files = []
        try:
            if self.provider_type == ProviderTypeEnum.GOOGLE_DRIVE:
                if self.credentials.get('refresh_token'):
                    creds = google_credentials.Credentials(
                        token=None,
                        refresh_token=self.credentials.get('refresh_token'),
                        client_id=self.credentials.get('client_id'),
                        client_secret=self.credentials.get('client_secret'),
                        token_uri='https://oauth2.googleapis.com/token',
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                else:
                    service_account_info = json.loads(self.credentials.get('service_account_json', '{}'))
                    creds = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                drive_service = build('drive', 'v3', credentials=creds)
                
                folder_id = self.credentials.get('folder_id')
                q = "mimeType contains 'image/'"
                if folder_id:
                    q += f" and '{folder_id}' in parents"
                    
                results = drive_service.files().list(
                    q=q,
                    fields="files(id, name, mimeType, webViewLink, webContentLink)"
                ).execute()
                
                for item in results.get('files', []):
                    files.append({
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'url': item.get('webViewLink'),
                        'mime_type': item.get('mimeType')
                    })
                    
            elif self.provider_type == ProviderTypeEnum.AWS_S3:
                s3 = boto3.client(
                    's3',
                    region_name=self.credentials.get('region', 'us-east-1'),
                    aws_access_key_id=self.credentials.get('access_key'),
                    aws_secret_access_key=self.credentials.get('secret_key')
                )
                bucket = self.credentials.get('bucket')
                response = s3.list_objects_v2(Bucket=bucket)
                if 'Contents' in response:
                    for item in response['Contents']:
                        key = item['Key']
                        # Basic image filter
                        if key.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                            files.append({
                                'id': key,
                                'name': key.split('/')[-1],
                                'url': self.get_url(key)
                            })
                            
            elif self.provider_type == ProviderTypeEnum.SUPABASE:
                supabase_url = self.credentials.get('supabase_url')
                supabase_key = self.credentials.get('supabase_key')
                bucket = self.credentials.get('supabase_bucket')
                
                url = f"{supabase_url}/storage/v1/object/list/{bucket}"
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "apikey": supabase_key,
                    "Content-Type": "application/json",
                }
                # Empty prefix lists root directory
                resp = requests.post(url, headers=headers, json={"prefix": "", "limit": 1000}, timeout=30)
                if resp.status_code == 200:
                    for item in resp.json():
                        name = item.get('name')
                        if name and name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and not name.startswith('.'):
                            files.append({
                                'id': name,
                                'name': name.split('/')[-1],
                                'url': self.get_url(name)
                            })
                            
            elif self.provider_type == ProviderTypeEnum.CLOUDINARY:
                cloudinary.config(
                    cloud_name=self.credentials.get('cloud_name'),
                    api_key=self.credentials.get('api_key'),
                    api_secret=self.credentials.get('api_secret')
                )
                import cloudinary.api
                resp = cloudinary.api.resources(resource_type="image", max_results=100)
                for item in resp.get('resources', []):
                    files.append({
                        'id': item.get('public_id') + '.' + item.get('format'),
                        'name': item.get('public_id').split('/')[-1] + '.' + item.get('format'),
                        'url': item.get('secure_url')
                    })
        except Exception as e:
            print(f"Failed to list files for {self.provider_type}: {e}")
            
        return files

    def download_file(self, file_id: str) -> bytes:
        """
        Download a file from the target storage into memory.
        """
        try:
            if self.provider_type == ProviderTypeEnum.GOOGLE_DRIVE:
                if self.credentials.get('refresh_token'):
                    creds = google_credentials.Credentials(
                        token=None,
                        refresh_token=self.credentials.get('refresh_token'),
                        client_id=self.credentials.get('client_id'),
                        client_secret=self.credentials.get('client_secret'),
                        token_uri='https://oauth2.googleapis.com/token',
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                else:
                    service_account_info = json.loads(self.credentials.get('service_account_json', '{}'))
                    creds = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                drive_service = build('drive', 'v3', credentials=creds)
                
                request = drive_service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                from googleapiclient.http import MediaIoBaseDownload
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                return fh.getvalue()
                
            elif self.provider_type == ProviderTypeEnum.AWS_S3:
                s3 = boto3.client(
                    's3',
                    region_name=self.credentials.get('region', 'us-east-1'),
                    aws_access_key_id=self.credentials.get('access_key'),
                    aws_secret_access_key=self.credentials.get('secret_key')
                )
                bucket = self.credentials.get('bucket')
                response = s3.get_object(Bucket=bucket, Key=file_id)
                return response['Body'].read()
                
            elif self.provider_type == ProviderTypeEnum.SUPABASE:
                supabase_url = self.credentials.get('supabase_url')
                supabase_key = self.credentials.get('supabase_key')
                bucket = self.credentials.get('supabase_bucket')
                
                url = f"{supabase_url}/storage/v1/object/public/{bucket}/{file_id}"
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200:
                    return resp.content
                else:
                    # Try authenticated download if public fails
                    url = f"{supabase_url}/storage/v1/object/{bucket}/{file_id}"
                    headers = {
                        "Authorization": f"Bearer {supabase_key}",
                        "apikey": supabase_key,
                    }
                    resp = requests.get(url, headers=headers, timeout=60)
                    return resp.content
                    
            elif self.provider_type == ProviderTypeEnum.CLOUDINARY:
                # Need to download via the secure_url
                cloudinary.config(
                    cloud_name=self.credentials.get('cloud_name'),
                    api_key=self.credentials.get('api_key'),
                    api_secret=self.credentials.get('api_secret')
                )
                import cloudinary.api
                public_id = file_id.split('.')[0]
                details = cloudinary.api.resource(public_id)
                resp = requests.get(details['secure_url'], timeout=60)
                return resp.content
                
        except Exception as e:
            print(f"Failed to download file {file_id} for {self.provider_type}: {e}")
            return b""
        
        return b""

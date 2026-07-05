import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

export interface User {
  id: string;
  username: string;
  email: string;
  password_hash: string;
  role: 'ADMIN' | 'USER';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Folder {
  id: string;
  parent_id: string | null;
  owner_id: string;
  name: string;
  created_at: string;
}

export interface FileRecord {
  id: string;
  owner_id: string;
  folder_id: string | null;
  original_name: string;
  stored_name: string;
  extension: string;
  mime_type: string;
  file_size: number;
  sha256: string;
  storage_path: string;
  thumbnail_path: string | null;
  upload_status: 'PENDING' | 'COMPLETED' | 'FAILED';
  is_favorite: boolean;
  date_taken: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

interface DatabaseSchema {
  users: User[];
  folders: Folder[];
  files: FileRecord[];
}

const DB_DIR = path.resolve(process.cwd(), 'database');
const DB_FILE = path.join(DB_DIR, 'db.json');
const UPLOADS_DIR = path.resolve(process.cwd(), 'uploads');
const THUMBNAILS_DIR = path.resolve(process.cwd(), 'thumbnails');
const PREVIEWS_DIR = path.resolve(process.cwd(), 'previews');

class JsonDatabase {
  private data: DatabaseSchema = { users: [], folders: [], files: [] };

  constructor() {
    this.init();
  }

  private init() {
    // Ensure directories exist
    if (!fs.existsSync(DB_DIR)) {
      fs.mkdirSync(DB_DIR, { recursive: true });
    }
    if (!fs.existsSync(UPLOADS_DIR)) {
      fs.mkdirSync(UPLOADS_DIR, { recursive: true });
    }
    if (!fs.existsSync(THUMBNAILS_DIR)) {
      fs.mkdirSync(THUMBNAILS_DIR, { recursive: true });
    }
    if (!fs.existsSync(PREVIEWS_DIR)) {
      fs.mkdirSync(PREVIEWS_DIR, { recursive: true });
    }

    // Load or create db.json
    if (fs.existsSync(DB_FILE)) {
      try {
        const raw = fs.readFileSync(DB_FILE, 'utf-8');
        this.data = JSON.parse(raw);
      } catch (e) {
        console.error('Failed to parse database file, initializing empty:', e);
        this.data = { users: [], folders: [], files: [] };
      }
    } else {
      this.data = { users: [], folders: [], files: [] };
      this.save();
    }

    // Ensure default admin user exists
    let admin = this.data.users.find(u => u.username === 'admin');
    if (!admin) {
      // password is 'admin' (hashed)
      // bcryptjs hash for 'admin': $2a$10$tMvM1N3L6rG/8.RzZ5mYfeFmH7fS.jB1T9Cg2s8y4Fm9QvK7nZ9V6
      // Let's use bcryptjs format hash
      const defaultHash = '$2a$10$tMvM1N3L6rG/8.RzZ5mYfeFmH7fS.jB1T9Cg2s8y4Fm9QvK7nZ9V6'; 
      admin = {
        id: 'admin-id-1234-5678',
        username: 'admin',
        email: 'admin@media-server.local',
        password_hash: defaultHash,
        role: 'ADMIN',
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      this.data.users.push(admin);
      this.save();
    }

    // Scan uploads directory to auto-import existing files
    this.scanAndImportUploads(admin.id);
  }

  private scanAndImportUploads(defaultOwnerId: string) {
    if (!fs.existsSync(UPLOADS_DIR)) return;

    const filesInUploads = fs.readdirSync(UPLOADS_DIR);
    let updated = false;

    for (const filename of filesInUploads) {
      if (filename === 'db.json' || filename.startsWith('temp_')) continue;
      const filepath = path.join(UPLOADS_DIR, filename);
      const stat = fs.statSync(filepath);

      if (stat.isFile()) {
        const ext = path.extname(filename);
        // Check if file is already registered in db
        const registered = this.data.files.find(f => f.stored_name === filename);
        if (!registered) {
          const sha256 = filename.split('.')[0] || crypto.randomUUID();
          const mimeType = this.guessMimeType(filename);
          
          const fileRecord: FileRecord = {
            id: crypto.randomUUID(),
            owner_id: defaultOwnerId,
            folder_id: null,
            original_name: filename,
            stored_name: filename,
            extension: ext,
            mime_type: mimeType,
            file_size: stat.size,
            sha256: sha256,
            storage_path: `/uploads/${filename}`,
            thumbnail_path: `/thumbnails/${filename}`,
            upload_status: 'COMPLETED',
            is_favorite: false,
            date_taken: null,
            deleted_at: null,
            created_at: stat.birthtime.toISOString(),
            updated_at: stat.mtime.toISOString()
          };
          this.data.files.push(fileRecord);
          updated = true;
          console.log(`Auto-registered existing file: ${filename}`);
        }
      }
    }

    if (updated) {
      this.save();
    }
  }

  private guessMimeType(filename: string): string {
    const ext = path.extname(filename).toLowerCase();
    switch (ext) {
      case '.jpg':
      case '.jpeg':
        return 'image/jpeg';
      case '.png':
        return 'image/png';
      case '.gif':
        return 'image/gif';
      case '.webp':
        return 'image/webp';
      case '.mp4':
        return 'video/mp4';
      case '.webm':
        return 'video/webm';
      case '.pdf':
        return 'application/pdf';
      default:
        return 'application/octet-stream';
    }
  }

  public save() {
    try {
      fs.writeFileSync(DB_FILE, JSON.stringify(this.data, null, 2), 'utf-8');
    } catch (e) {
      console.error('Failed to write database file:', e);
    }
  }

  // User queries
  public getUsers(): User[] {
    return this.data.users;
  }

  public getUserById(id: string): User | undefined {
    return this.data.users.find(u => u.id === id);
  }

  public getUserByUsername(username: string): User | undefined {
    return this.data.users.find(u => u.username.toLowerCase() === username.toLowerCase());
  }

  public addUser(user: User) {
    this.data.users.push(user);
    this.save();
  }

  public removeUser(id: string) {
    this.data.users = this.data.users.filter(u => u.id !== id);
    this.data.files = this.data.files.filter(f => f.owner_id !== id);
    this.data.folders = this.data.folders.filter(fd => fd.owner_id !== id);
    this.save();
  }

  // Folder queries
  public getFolders(ownerId: string): Folder[] {
    return this.data.folders.filter(f => f.owner_id === ownerId);
  }

  public getFolderById(id: string, ownerId: string): Folder | undefined {
    return this.data.folders.find(f => f.id === id && f.owner_id === ownerId);
  }

  public addFolder(folder: Folder) {
    this.data.folders.push(folder);
    this.save();
  }

  public removeFolder(id: string, ownerId: string) {
    this.data.folders = this.data.folders.filter(f => !(f.id === id && f.owner_id === ownerId));
    // Detach files
    this.data.files = this.data.files.map(file => {
      if (file.folder_id === id && file.owner_id === ownerId) {
        return { ...file, folder_id: null };
      }
      return file;
    });
    this.save();
  }

  // File queries
  public getFiles(ownerId: string): FileRecord[] {
    return this.data.files.filter(f => f.owner_id === ownerId);
  }

  public getFileById(id: string, ownerId: string): FileRecord | undefined {
    return this.data.files.find(f => f.id === id && f.owner_id === ownerId);
  }

  public addFile(file: FileRecord) {
    this.data.files.push(file);
    this.save();
  }

  public removeFile(id: string, ownerId: string) {
    this.data.files = this.data.files.filter(f => !(f.id === id && f.owner_id === ownerId));
    this.save();
  }

  public updateFile(file: FileRecord) {
    const idx = this.data.files.findIndex(f => f.id === file.id);
    if (idx !== -1) {
      this.data.files[idx] = file;
      this.save();
    }
  }

  public bulkMoveFiles(fileIds: string[], folderId: string | null, ownerId: string) {
    this.data.files = this.data.files.map(file => {
      if (fileIds.includes(file.id) && file.owner_id === ownerId) {
        return { ...file, folder_id: folderId };
      }
      return file;
    });
    this.save();
  }
}

export const db = new JsonDatabase();

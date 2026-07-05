import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import pg from 'pg';

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

export interface DatabaseProvider {
  init(): Promise<void>;
  getUsers(): Promise<User[]>;
  getUserById(id: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  addUser(user: User): Promise<void>;
  removeUser(id: string): Promise<void>;
  getFolders(ownerId: string): Promise<Folder[]>;
  getFolderById(id: string, ownerId: string): Promise<Folder | undefined>;
  addFolder(folder: Folder): Promise<void>;
  removeFolder(id: string, ownerId: string): Promise<void>;
  getFiles(ownerId: string): Promise<FileRecord[]>;
  getFileById(id: string, ownerId: string): Promise<FileRecord | undefined>;
  addFile(file: FileRecord): Promise<void>;
  removeFile(id: string, ownerId: string): Promise<void>;
  updateFile(file: FileRecord): Promise<void>;
  bulkMoveFiles(fileIds: string[], folderId: string | null, ownerId: string): Promise<void>;
  save(): Promise<void>;
}

const DB_DIR = path.resolve(process.cwd(), 'database');
const DB_FILE = path.join(DB_DIR, 'db.json');
const UPLOADS_DIR = path.resolve(process.cwd(), 'uploads');
const THUMBNAILS_DIR = path.resolve(process.cwd(), 'thumbnails');
const PREVIEWS_DIR = path.resolve(process.cwd(), 'previews');

const DEFAULT_ADMIN: User = {
  id: 'admin-id-1234-5678',
  username: 'admin',
  email: 'admin@media-server.local',
  password_hash: '$2a$10$tMvM1N3L6rG/8.RzZ5mYfeFmH7fS.jB1T9Cg2s8y4Fm9QvK7nZ9V6', // bcrypt for 'admin'
  role: 'ADMIN',
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString()
};

function guessMimeType(filename: string): string {
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

// ------------------------------------------------------------
// LOCAL JSON DATABASE PROVIDER
// ------------------------------------------------------------
class JsonDatabaseProvider implements DatabaseProvider {
  private data: { users: User[]; folders: Folder[]; files: FileRecord[] } = { users: [], folders: [], files: [] };

  public async init() {
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

    if (fs.existsSync(DB_FILE)) {
      try {
        const raw = fs.readFileSync(DB_FILE, 'utf-8');
        this.data = JSON.parse(raw);
      } catch (e) {
        console.error('Failed to parse local database file, initializing empty:', e);
        this.data = { users: [], folders: [], files: [] };
      }
    } else {
      this.data = { users: [], folders: [], files: [] };
      await this.save();
    }

    let admin = this.data.users.find(u => u.username === 'admin');
    if (!admin) {
      admin = { ...DEFAULT_ADMIN };
      this.data.users.push(admin);
      await this.save();
    }

    await this.scanAndImportUploads(admin.id);
  }

  private async scanAndImportUploads(defaultOwnerId: string) {
    if (!fs.existsSync(UPLOADS_DIR)) return;

    const filesInUploads = fs.readdirSync(UPLOADS_DIR);
    let updated = false;

    for (const filename of filesInUploads) {
      if (filename === 'db.json' || filename.startsWith('temp_') || filename === 'temp') continue;
      const filepath = path.join(UPLOADS_DIR, filename);
      const stat = fs.statSync(filepath);

      if (stat.isFile()) {
        const ext = path.extname(filename);
        const registered = this.data.files.find(f => f.stored_name === filename);
        if (!registered) {
          const sha256 = filename.split('.')[0] || crypto.randomUUID();
          const mimeType = guessMimeType(filename);
          
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
          console.log(`Auto-registered local file in JSON DB: ${filename}`);
        }
      }
    }

    if (updated) {
      await this.save();
    }
  }

  public async save() {
    try {
      fs.writeFileSync(DB_FILE, JSON.stringify(this.data, null, 2), 'utf-8');
    } catch (e) {
      console.error('Failed to write database file:', e);
    }
  }

  public async getUsers(): Promise<User[]> {
    return this.data.users;
  }

  public async getUserById(id: string): Promise<User | undefined> {
    return this.data.users.find(u => u.id === id);
  }

  public async getUserByUsername(username: string): Promise<User | undefined> {
    return this.data.users.find(u => u.username.toLowerCase() === username.toLowerCase());
  }

  public async addUser(user: User): Promise<void> {
    this.data.users.push(user);
    await this.save();
  }

  public async removeUser(id: string): Promise<void> {
    this.data.users = this.data.users.filter(u => u.id !== id);
    this.data.files = this.data.files.filter(f => f.owner_id !== id);
    this.data.folders = this.data.folders.filter(fd => fd.owner_id !== id);
    await this.save();
  }

  public async getFolders(ownerId: string): Promise<Folder[]> {
    return this.data.folders.filter(f => f.owner_id === ownerId);
  }

  public async getFolderById(id: string, ownerId: string): Promise<Folder | undefined> {
    return this.data.folders.find(f => f.id === id && f.owner_id === ownerId);
  }

  public async addFolder(folder: Folder): Promise<void> {
    this.data.folders.push(folder);
    await this.save();
  }

  public async removeFolder(id: string, ownerId: string): Promise<void> {
    this.data.folders = this.data.folders.filter(f => !(f.id === id && f.owner_id === ownerId));
    this.data.files = this.data.files.map(file => {
      if (file.folder_id === id && file.owner_id === ownerId) {
        return { ...file, folder_id: null };
      }
      return file;
    });
    await this.save();
  }

  public async getFiles(ownerId: string): Promise<FileRecord[]> {
    return this.data.files.filter(f => f.owner_id === ownerId);
  }

  public async getFileById(id: string, ownerId: string): Promise<FileRecord | undefined> {
    return this.data.files.find(f => f.id === id && f.owner_id === ownerId);
  }

  public async addFile(file: FileRecord): Promise<void> {
    this.data.files.push(file);
    await this.save();
  }

  public async removeFile(id: string, ownerId: string): Promise<void> {
    this.data.files = this.data.files.filter(f => !(f.id === id && f.owner_id === ownerId));
    await this.save();
  }

  public async updateFile(file: FileRecord): Promise<void> {
    const idx = this.data.files.findIndex(f => f.id === file.id);
    if (idx !== -1) {
      this.data.files[idx] = file;
      await this.save();
    }
  }

  public async bulkMoveFiles(fileIds: string[], folderId: string | null, ownerId: string): Promise<void> {
    this.data.files = this.data.files.map(file => {
      if (fileIds.includes(file.id) && file.owner_id === ownerId) {
        return { ...file, folder_id: folderId };
      }
      return file;
    });
    await this.save();
  }
}

// ------------------------------------------------------------
// POSTGRESQL DATABASE PROVIDER (SUPABASE)
// ------------------------------------------------------------
class PostgresDatabaseProvider implements DatabaseProvider {
  private pool: pg.Pool;

  constructor(connectionString: string) {
    // Gracefully handle standard port (5432) mapping to pooling port (6543) if it is blocked
    let parsedUrl = connectionString;
    if (parsedUrl.includes(':5432/')) {
      parsedUrl = parsedUrl.replace(':5432/', ':6543/');
    }

    this.pool = new pg.Pool({
      connectionString: parsedUrl,
      ssl: { rejectUnauthorized: false },
      connectionTimeoutMillis: 5000, // Timeout fast if DB is paused so we fall back quickly
    });
  }

  public async init() {
    // Create schemas if they do not exist
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(50) DEFAULT 'USER',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS folders (
        id VARCHAR(36) PRIMARY KEY,
        parent_id VARCHAR(36) REFERENCES folders(id) ON DELETE SET NULL,
        owner_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS files (
        id VARCHAR(36) PRIMARY KEY,
        owner_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
        folder_id VARCHAR(36) REFERENCES folders(id) ON DELETE SET NULL,
        original_name VARCHAR(255) NOT NULL,
        stored_name VARCHAR(255) UNIQUE NOT NULL,
        extension VARCHAR(50) NOT NULL,
        mime_type VARCHAR(100) NOT NULL,
        file_size BIGINT NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        width INTEGER,
        height INTEGER,
        storage_path VARCHAR(512) NOT NULL,
        thumbnail_path VARCHAR(512),
        upload_status VARCHAR(50) DEFAULT 'PENDING',
        is_favorite BOOLEAN DEFAULT FALSE,
        date_taken TIMESTAMP,
        deleted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // Ensure default admin user exists
    await this.pool.query(`
      INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      ON CONFLICT (username) DO NOTHING
    `, [
      DEFAULT_ADMIN.id,
      DEFAULT_ADMIN.username,
      DEFAULT_ADMIN.email,
      DEFAULT_ADMIN.password_hash,
      DEFAULT_ADMIN.role,
      DEFAULT_ADMIN.is_active,
      DEFAULT_ADMIN.created_at,
      DEFAULT_ADMIN.updated_at
    ]);

    // Local uploads folders scanning & automatic sync
    await this.scanAndImportUploads(DEFAULT_ADMIN.id);
  }

  private async scanAndImportUploads(defaultOwnerId: string) {
    if (!fs.existsSync(UPLOADS_DIR)) return;

    const filesInUploads = fs.readdirSync(UPLOADS_DIR);
    for (const filename of filesInUploads) {
      if (filename === 'db.json' || filename.startsWith('temp_') || filename === 'temp') continue;
      const filepath = path.join(UPLOADS_DIR, filename);
      const stat = fs.statSync(filepath);

      if (stat.isFile()) {
        const ext = path.extname(filename);
        const registeredRes = await this.pool.query('SELECT 1 FROM files WHERE stored_name = $1', [filename]);
        
        if (registeredRes.rows.length === 0) {
          const sha256 = filename.split('.')[0] || crypto.randomUUID();
          const mimeType = guessMimeType(filename);
          
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
          
          await this.addFile(fileRecord);
          console.log(`Auto-registered local file in PostgreSQL DB: ${filename}`);
        }
      }
    }
  }

  public async save() {
    // No-op for Postgres as queries are committed instantly
  }

  public async getUsers(): Promise<User[]> {
    const res = await this.pool.query('SELECT * FROM users');
    return res.rows.map(row => ({
      id: row.id,
      username: row.username,
      email: row.email,
      password_hash: row.password_hash,
      role: row.role as 'ADMIN' | 'USER',
      is_active: row.is_active,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
      updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : '',
    }));
  }

  public async getUserById(id: string): Promise<User | undefined> {
    const res = await this.pool.query('SELECT * FROM users WHERE id = $1', [id]);
    if (res.rows.length === 0) return undefined;
    const row = res.rows[0];
    return {
      id: row.id,
      username: row.username,
      email: row.email,
      password_hash: row.password_hash,
      role: row.role as 'ADMIN' | 'USER',
      is_active: row.is_active,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
      updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : '',
    };
  }

  public async getUserByUsername(username: string): Promise<User | undefined> {
    const res = await this.pool.query('SELECT * FROM users WHERE LOWER(username) = LOWER($1)', [username]);
    if (res.rows.length === 0) return undefined;
    const row = res.rows[0];
    return {
      id: row.id,
      username: row.username,
      email: row.email,
      password_hash: row.password_hash,
      role: row.role as 'ADMIN' | 'USER',
      is_active: row.is_active,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
      updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : '',
    };
  }

  public async addUser(user: User): Promise<void> {
    await this.pool.query(
      `INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       ON CONFLICT (username) DO NOTHING`,
      [user.id, user.username, user.email, user.password_hash, user.role, user.is_active, user.created_at, user.updated_at]
    );
  }

  public async removeUser(id: string): Promise<void> {
    await this.pool.query('DELETE FROM users WHERE id = $1', [id]);
  }

  public async getFolders(ownerId: string): Promise<Folder[]> {
    const res = await this.pool.query('SELECT * FROM folders WHERE owner_id = $1', [ownerId]);
    return res.rows.map(row => ({
      id: row.id,
      parent_id: row.parent_id,
      owner_id: row.owner_id,
      name: row.name,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
    }));
  }

  public async getFolderById(id: string, ownerId: string): Promise<Folder | undefined> {
    const res = await this.pool.query('SELECT * FROM folders WHERE id = $1 AND owner_id = $2', [id, ownerId]);
    if (res.rows.length === 0) return undefined;
    const row = res.rows[0];
    return {
      id: row.id,
      parent_id: row.parent_id,
      owner_id: row.owner_id,
      name: row.name,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
    };
  }

  public async addFolder(folder: Folder): Promise<void> {
    await this.pool.query(
      `INSERT INTO folders (id, parent_id, owner_id, name, created_at)
       VALUES ($1, $2, $3, $4, $5)`,
      [folder.id, folder.parent_id, folder.owner_id, folder.name, folder.created_at]
    );
  }

  public async removeFolder(id: string, ownerId: string): Promise<void> {
    await this.pool.query('DELETE FROM folders WHERE id = $1 AND owner_id = $2', [id, ownerId]);
  }

  public async getFiles(ownerId: string): Promise<FileRecord[]> {
    const res = await this.pool.query('SELECT * FROM files WHERE owner_id = $1', [ownerId]);
    return res.rows.map(row => ({
      id: row.id,
      owner_id: row.owner_id,
      folder_id: row.folder_id,
      original_name: row.original_name,
      stored_name: row.stored_name,
      extension: row.extension,
      mime_type: row.mime_type,
      file_size: Number(row.file_size),
      sha256: row.sha256,
      storage_path: row.storage_path,
      thumbnail_path: row.thumbnail_path,
      upload_status: row.upload_status as 'PENDING' | 'COMPLETED' | 'FAILED',
      is_favorite: row.is_favorite,
      date_taken: row.date_taken ? new Date(row.date_taken).toISOString() : null,
      deleted_at: row.deleted_at ? new Date(row.deleted_at).toISOString() : null,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
      updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : '',
    }));
  }

  public async getFileById(id: string, ownerId: string): Promise<FileRecord | undefined> {
    const res = await this.pool.query('SELECT * FROM files WHERE id = $1 AND owner_id = $2', [id, ownerId]);
    if (res.rows.length === 0) return undefined;
    const row = res.rows[0];
    return {
      id: row.id,
      owner_id: row.owner_id,
      folder_id: row.folder_id,
      original_name: row.original_name,
      stored_name: row.stored_name,
      extension: row.extension,
      mime_type: row.mime_type,
      file_size: Number(row.file_size),
      sha256: row.sha256,
      storage_path: row.storage_path,
      thumbnail_path: row.thumbnail_path,
      upload_status: row.upload_status as 'PENDING' | 'COMPLETED' | 'FAILED',
      is_favorite: row.is_favorite,
      date_taken: row.date_taken ? new Date(row.date_taken).toISOString() : null,
      deleted_at: row.deleted_at ? new Date(row.deleted_at).toISOString() : null,
      created_at: row.created_at ? new Date(row.created_at).toISOString() : '',
      updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : '',
    };
  }

  public async addFile(file: FileRecord): Promise<void> {
    await this.pool.query(
      `INSERT INTO files (id, owner_id, folder_id, original_name, stored_name, extension, mime_type, file_size, sha256, storage_path, thumbnail_path, upload_status, is_favorite, date_taken, deleted_at, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
       ON CONFLICT (stored_name) DO UPDATE SET
         folder_id = EXCLUDED.folder_id,
         upload_status = EXCLUDED.upload_status,
         is_favorite = EXCLUDED.is_favorite,
         deleted_at = EXCLUDED.deleted_at,
         updated_at = EXCLUDED.updated_at`,
      [
        file.id, file.owner_id, file.folder_id, file.original_name, file.stored_name,
        file.extension, file.mime_type, file.file_size, file.sha256, file.storage_path,
        file.thumbnail_path, file.upload_status, file.is_favorite, file.date_taken,
        file.deleted_at, file.created_at, file.updated_at
      ]
    );
  }

  public async removeFile(id: string, ownerId: string): Promise<void> {
    await this.pool.query('DELETE FROM files WHERE id = $1 AND owner_id = $2', [id, ownerId]);
  }

  public async updateFile(file: FileRecord): Promise<void> {
    await this.pool.query(
      `UPDATE files SET
         folder_id = $1,
         upload_status = $2,
         is_favorite = $3,
         date_taken = $4,
         deleted_at = $5,
         updated_at = $6
       WHERE id = $7`,
      [file.folder_id, file.upload_status, file.is_favorite, file.date_taken, file.deleted_at, file.updated_at, file.id]
    );
  }

  public async bulkMoveFiles(fileIds: string[], folderId: string | null, ownerId: string): Promise<void> {
    await this.pool.query(
      `UPDATE files SET folder_id = $1, updated_at = NOW() WHERE id = ANY($2) AND owner_id = $3`,
      [folderId, fileIds, ownerId]
    );
  }
}

// ------------------------------------------------------------
// UNIFIED DYNAMIC DATABASE LAYER (EXPORTS SINGLE INTERFACE)
// ------------------------------------------------------------
class UnifiedDatabase implements DatabaseProvider {
  private activeProvider!: DatabaseProvider;

  constructor() {
    // We defer actual initialization to the async init method
  }

  public async init() {
    const dbUrl = process.env.DATABASE_URL;

    if (dbUrl) {
      console.log('Detected DATABASE_URL. Attempting to initialize Supabase PostgreSQL connection...');
      try {
        const pgProvider = new PostgresDatabaseProvider(dbUrl);
        await pgProvider.init();
        this.activeProvider = pgProvider;
        console.log('✅ Connected successfully to Supabase PostgreSQL database.');
        return;
      } catch (err: any) {
        console.error('❌ Failed to connect to Supabase PostgreSQL:', err.message);
        console.log('⚠️ Database might be paused or unreachable. Falling back to local JSON database...');
      }
    } else {
      console.log('No DATABASE_URL configured. Using local JSON database...');
    }

    const jsonProvider = new JsonDatabaseProvider();
    await jsonProvider.init();
    this.activeProvider = jsonProvider;
    console.log('✅ Local JSON database active.');
  }

  public async getUsers(): Promise<User[]> {
    return this.activeProvider.getUsers();
  }

  public async getUserById(id: string): Promise<User | undefined> {
    return this.activeProvider.getUserById(id);
  }

  public async getUserByUsername(username: string): Promise<User | undefined> {
    return this.activeProvider.getUserByUsername(username);
  }

  public async addUser(user: User): Promise<void> {
    return this.activeProvider.addUser(user);
  }

  public async removeUser(id: string): Promise<void> {
    return this.activeProvider.removeUser(id);
  }

  public async getFolders(ownerId: string): Promise<Folder[]> {
    return this.activeProvider.getFolders(ownerId);
  }

  public async getFolderById(id: string, ownerId: string): Promise<Folder | undefined> {
    return this.activeProvider.getFolderById(id, ownerId);
  }

  public async addFolder(folder: Folder): Promise<void> {
    return this.activeProvider.addFolder(folder);
  }

  public async removeFolder(id: string, ownerId: string): Promise<void> {
    return this.activeProvider.removeFolder(id, ownerId);
  }

  public async getFiles(ownerId: string): Promise<FileRecord[]> {
    return this.activeProvider.getFiles(ownerId);
  }

  public async getFileById(id: string, ownerId: string): Promise<FileRecord | undefined> {
    return this.activeProvider.getFileById(id, ownerId);
  }

  public async addFile(file: FileRecord): Promise<void> {
    return this.activeProvider.addFile(file);
  }

  public async removeFile(id: string, ownerId: string): Promise<void> {
    return this.activeProvider.removeFile(id, ownerId);
  }

  public async updateFile(file: FileRecord): Promise<void> {
    return this.activeProvider.updateFile(file);
  }

  public async bulkMoveFiles(fileIds: string[], folderId: string | null, ownerId: string): Promise<void> {
    return this.activeProvider.bulkMoveFiles(fileIds, folderId, ownerId);
  }

  public async save(): Promise<void> {
    return this.activeProvider.save();
  }
}

export const db = new UnifiedDatabase();

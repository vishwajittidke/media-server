import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import multer from 'multer';
import { createServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { createServer as createViteServer } from 'vite';

import { db } from './src/server/db.js';
import { hashPassword, comparePassword, generateToken, verifyToken } from './src/server/auth.js';

const app = express();
const httpServer = createServer(app);
const PORT = 3000;

// Ensure directories exist
const UPLOADS_DIR = path.resolve(process.cwd(), 'uploads');
const THUMBNAILS_DIR = path.resolve(process.cwd(), 'thumbnails');
const PREVIEWS_DIR = path.resolve(process.cwd(), 'previews');

if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });
if (!fs.existsSync(THUMBNAILS_DIR)) fs.mkdirSync(THUMBNAILS_DIR, { recursive: true });
if (!fs.existsSync(PREVIEWS_DIR)) fs.mkdirSync(PREVIEWS_DIR, { recursive: true });

// Setup Multer upload configuration
const upload = multer({ dest: path.join(UPLOADS_DIR, 'temp') });

// CORS Configuration
app.use(cors({
  origin: '*',
  credentials: true,
}));

// Express parsers
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static assets from uploads/thumbnails/previews
app.use('/uploads', express.static(UPLOADS_DIR));
app.use('/thumbnails', express.static(UPLOADS_DIR)); // Fallback serving original as thumbnail
app.use('/previews', express.static(UPLOADS_DIR));   // Fallback serving original as preview

// Middleware to protect routes via JWT (now fully asynchronous)
const authenticate = async (req: any, res: any, next: any) => {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const token = authHeader.split(' ')[1];
  const userId = verifyToken(token);
  if (!userId) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const user = await db.getUserById(userId);
  if (!user || !user.is_active) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  req.user = user;
  next();
};

// ==================== WEBSOCKET SERVER ====================
const wss = new WebSocketServer({ noServer: true });
const clients = new Map<string, Set<WebSocket>>();

wss.on('connection', (ws: WebSocket, userId: string) => {
  if (!clients.has(userId)) {
    clients.set(userId, new Set());
  }
  clients.get(userId)!.add(ws);

  ws.on('close', () => {
    const userClients = clients.get(userId);
    if (userClients) {
      userClients.delete(ws);
      if (userClients.size === 0) {
        clients.delete(userId);
      }
    }
  });
});

const broadcastToUser = (userId: string, message: any) => {
  const userClients = clients.get(userId);
  if (userClients) {
    const rawMessage = JSON.stringify(message);
    userClients.forEach(ws => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(rawMessage);
      }
    });
  }
};

// Handle HTTP Upgrade to WebSocket
httpServer.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url || '', `http://${request.headers.host}`);
  const pathname = url.pathname; // /api/v1/ws/:token

  const parts = pathname.split('/');
  const token = parts[parts.length - 1];

  if (pathname.includes('/api/v1/ws') && token) {
    const userId = verifyToken(token);
    if (userId) {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, userId);
      });
    } else {
      socket.destroy();
    }
  } else {
    socket.destroy();
  }
});

// ==================== AUTH API ENDPOINTS ====================

// Support urlencoded because of URLSearchParams used in client
app.post('/api/v1/auth/login', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password required' });
  }

  let user = await db.getUserByUsername(username);
  if (!user) {
    // Graceful auto-registration for any new user logged in for the first time
    const users = await db.getUsers();
    const isFirst = users.length === 0;
    user = {
      id: crypto.randomUUID(),
      username,
      email: `${username}@media-server.local`,
      password_hash: hashPassword(password),
      role: isFirst ? 'ADMIN' : 'USER',
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    await db.addUser(user);
    console.log(`Auto-registered new user: ${username}`);
  } else {
    if (!comparePassword(password, user.password_hash)) {
      return res.status(400).json({ detail: 'Incorrect username or password' });
    }
  }

  const token = generateToken(user.id);
  res.json({
    access_token: token,
    token_type: 'bearer',
  });
});

app.get('/api/v1/auth/me', authenticate, (req: any, res) => {
  res.json({
    id: req.user.id,
    username: req.user.username,
    email: req.user.email,
    role: req.user.role,
    is_active: req.user.is_active,
  });
});

app.put('/api/v1/auth/change-password', authenticate, async (req: any, res) => {
  const { old_password, new_password } = req.body;
  if (!old_password || !new_password) {
    return res.status(400).json({ error: 'Old and new passwords required' });
  }

  if (!comparePassword(old_password, req.user.password_hash)) {
    return res.status(400).json({ detail: 'Incorrect old password' });
  }

  req.user.password_hash = hashPassword(new_password);
  req.user.updated_at = new Date().toISOString();
  await db.updateFile(req.user); // updateFile handles any schema modifications or we can just save
  await db.save();

  res.json({ status: 'success' });
});

app.delete('/api/v1/auth/me', authenticate, async (req: any, res) => {
  await db.removeUser(req.user.id);
  res.status(204).end();
});

// ==================== ALBUM (FOLDER) API ENDPOINTS ====================

app.get('/api/v1/folders', authenticate, async (req: any, res) => {
  const folders = await db.getFolders(req.user.id);
  const files = (await db.getFiles(req.user.id)).filter(f => f.deleted_at === null);

  const result = folders.map(f => {
    // Find latest image in this folder for the cover url
    const folderFiles = files.filter(file => file.folder_id === f.id && file.mime_type.startsWith('image/'));
    const latestFile = folderFiles.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];

    return {
      id: f.id,
      name: f.name,
      parent_id: f.parent_id,
      owner_id: f.owner_id,
      created_at: f.created_at,
      cover_url: latestFile ? latestFile.thumbnail_path || latestFile.storage_path : null,
    };
  });

  res.json(result);
});

app.post('/api/v1/folders', authenticate, async (req: any, res) => {
  const { name, parent_id } = req.body;
  if (!name) {
    return res.status(400).json({ error: 'Album name required' });
  }

  const folder = {
    id: crypto.randomUUID(),
    parent_id: parent_id || null,
    owner_id: req.user.id,
    name,
    created_at: new Date().toISOString(),
  };

  await db.addFolder(folder);
  res.status(201).json(folder);
});

app.delete('/api/v1/folders/:id', authenticate, async (req: any, res) => {
  await db.removeFolder(req.params.id, req.user.id);
  res.status(204).end();
});

// ==================== FILE API ENDPOINTS ====================

// Route supports both trailing slash and normal path
const handleUpload = async (req: any, res: any) => {
  if (!req.files || req.files.length === 0) {
    return res.status(400).json({ error: 'No files uploaded' });
  }

  const folder_id = req.body.folder_id || null;
  const date_taken = req.body.date_taken || null;
  const uploaded_files_info: any[] = [];

  for (const file of req.files) {
    const ext = path.extname(file.originalname);
    const fileContent = fs.readFileSync(file.path);
    const file_hash = crypto.createHash('sha256').update(fileContent).digest('hex');

    // Check duplicate
    const files = (await db.getFiles(req.user.id)).filter(f => f.deleted_at === null);
    const existing = files.find(f => f.sha256 === file_hash);
    if (existing) {
      fs.unlinkSync(file.path);
      uploaded_files_info.push({"filename": file.originalname, "status": "duplicate", "id": existing.id});
      continue;
    }

    const stored_name = `${file_hash}${ext}`;
    const final_path = path.join(UPLOADS_DIR, stored_name);

    // Save locally
    fs.renameSync(file.path, final_path);

    const fileRecord = {
      id: crypto.randomUUID(),
      owner_id: req.user.id,
      folder_id,
      original_name: file.originalname,
      stored_name,
      extension: ext,
      mime_type: file.mimetype || 'application/octet-stream',
      file_size: file.size,
      sha256: file_hash,
      storage_path: `/uploads/${stored_name}`,
      thumbnail_path: `/thumbnails/${stored_name}`,
      upload_status: 'COMPLETED' as const,
      is_favorite: false,
      date_taken,
      deleted_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    await db.addFile(fileRecord);

    // Broadcast WebSocket
    broadcastToUser(req.user.id, {
      type: 'FILE_UPLOADED',
      file: {
        id: fileRecord.id,
        original_name: fileRecord.original_name,
        created_at: fileRecord.created_at,
      },
    });

    uploaded_files_info.push({
      filename: file.originalname,
      status: 'success',
      id: fileRecord.id,
    });
  }

  res.status(201).json({ uploaded: uploaded_files_info });
};

app.post('/api/v1/files', authenticate, upload.any(), handleUpload);
app.post('/api/v1/files/', authenticate, upload.any(), handleUpload);

app.get('/api/v1/files', authenticate, async (req: any, res) => {
  const folder_id = req.query.folder_id || null;
  const is_favorite = req.query.is_favorite === 'true';
  const skip = parseInt(req.query.skip as string) || 0;
  const limit = parseInt(req.query.limit as string) || 50;

  let files = (await db.getFiles(req.user.id)).filter(f => f.deleted_at === null);

  if (is_favorite) {
    files = files.filter(f => f.is_favorite);
  } else if (folder_id) {
    files = files.filter(f => f.folder_id === folder_id);
  } else {
    files = files.filter(f => f.folder_id === null);
  }

  // Sort by date_taken or created_at desc
  files.sort((a, b) => {
    const timeA = new Date(a.date_taken || a.created_at).getTime();
    const timeB = new Date(b.date_taken || b.created_at).getTime();
    return timeB - timeA;
  });

  const page = files.slice(skip, skip + limit);
  const responsePage = page.map(f => ({
    ...f,
    preview_url: f.storage_path,
    thumbnail_url: f.thumbnail_path || f.storage_path,
  }));
  res.json(responsePage);
});

// Recycle Bin lists
app.get('/api/v1/files/trash/list', authenticate, async (req: any, res) => {
  const skip = parseInt(req.query.skip as string) || 0;
  const limit = parseInt(req.query.limit as string) || 50;

  const files = (await db.getFiles(req.user.id)).filter(f => f.deleted_at !== null);

  files.sort((a, b) => {
    const timeA = new Date(a.deleted_at!).getTime();
    const timeB = new Date(b.deleted_at!).getTime();
    return timeB - timeA;
  });

  const page = files.slice(skip, skip + limit);
  const responsePage = page.map(f => ({
    ...f,
    preview_url: f.storage_path,
    thumbnail_url: f.thumbnail_path || f.storage_path,
  }));
  res.json(responsePage);
});

app.put('/api/v1/files/trash/:id/restore', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file) {
    return res.status(404).json({ error: 'File not found' });
  }

  file.deleted_at = null;
  file.updated_at = new Date().toISOString();
  await db.updateFile(file);
  await db.save();

  res.json({ status: 'ok' });
});

app.delete('/api/v1/files/trash/empty', authenticate, async (req: any, res) => {
  const files = (await db.getFiles(req.user.id)).filter(f => f.deleted_at !== null);

  for (const file of files) {
    const filepath = path.join(UPLOADS_DIR, file.stored_name);
    if (fs.existsSync(filepath)) {
      try {
        fs.unlinkSync(filepath);
      } catch (e) {}
    }
    await db.removeFile(file.id, req.user.id);
  }

  res.json({ status: 'ok', deleted_count: files.length });
});

app.delete('/api/v1/files/trash/:id/permanent', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file || file.deleted_at === null) {
    return res.status(404).json({ error: 'File not found in trash' });
  }

  const filepath = path.join(UPLOADS_DIR, file.stored_name);
  if (fs.existsSync(filepath)) {
    try {
      fs.unlinkSync(filepath);
    } catch (e) {}
  }

  await db.removeFile(file.id, req.user.id);
  res.status(204).end();
});

app.delete('/api/v1/files/:id', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file) {
    return res.status(404).json({ error: 'File not found' });
  }

  file.deleted_at = new Date().toISOString();
  file.updated_at = new Date().toISOString();
  await db.updateFile(file);
  await db.save();

  res.status(204).end();
});

app.put('/api/v1/files/:id/move', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file) {
    return res.status(404).json({ error: 'File not found' });
  }

  const { folder_id } = req.body;
  file.folder_id = folder_id || null;
  file.updated_at = new Date().toISOString();
  await db.updateFile(file);
  await db.save();

  res.json({ status: 'ok' });
});

app.put('/api/v1/files/bulk/move', authenticate, async (req: any, res) => {
  const { file_ids, folder_id } = req.body;
  if (!Array.isArray(file_ids)) {
    return res.status(400).json({ error: 'file_ids array is required' });
  }

  await db.bulkMoveFiles(file_ids, folder_id || null, req.user.id);
  res.json({ status: 'ok' });
});

app.put('/api/v1/files/:id/favorite', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file) {
    return res.status(404).json({ error: 'File not found' });
  }

  file.is_favorite = !file.is_favorite;
  file.updated_at = new Date().toISOString();
  await db.updateFile(file);
  await db.save();

  res.json({ status: 'ok', is_favorite: file.is_favorite });
});

app.get('/api/v1/files/download/:id', authenticate, async (req: any, res) => {
  const file = await db.getFileById(req.params.id, req.user.id);
  if (!file) {
    return res.status(404).json({ error: 'File not found' });
  }

  const filepath = path.join(UPLOADS_DIR, file.stored_name);
  if (!fs.existsSync(filepath)) {
    return res.status(404).json({ error: 'Physical file not found on disk' });
  }

  res.download(filepath, file.original_name);
});

// ==================== HEALTH / MISC ENDPOINTS ====================
app.get('/api/v1/health', (req, res) => {
  res.json({ status: 'ok', message: 'Service is live' });
});

app.head('/', (req, res) => {
  res.json({ status: 'ok', message: 'Media Server is running' });
});

// ==================== VITE & CLIENT ROUTING MIDDLEWARE ====================
async function start() {
  // Initialize unified database layer dynamically before launching server
  await db.init();

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`Full-stack server listening on http://0.0.0.0:${PORT}`);
  });
}

start();

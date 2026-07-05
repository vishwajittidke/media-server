import React, { useEffect, useState, useRef } from 'react';
import { Gallery as PhotoSwipeGallery, Item } from 'react-photoswipe-gallery';
import 'photoswipe/dist/photoswipe.css';
import exifr from 'exifr';

interface FileItem {
  id: string;
  original_name: string;
  stored_name: string;
  mime_type: string;
  created_at: string;
  storage_path?: string;
  thumbnail_url?: string;
  preview_url?: string;
  is_favorite?: boolean;
  date_taken?: string;
}

interface FolderItem {
  id: string;
  name: string;
  created_at: string;
  cover_url?: string;
}

interface GalleryProps {
  token: string;
  onLogout: () => void;
}

const Gallery: React.FC<GalleryProps> = ({ token, onLogout }) => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [activeTab, setActiveTab] = useState<'photos' | 'albums' | 'favorites'>('photos');
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [movingFileId, setMovingFileId] = useState<string | null>(null);
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ old: '', new: '' });
  const [uploading, setUploading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [dimensions, setDimensions] = useState<Record<string, {width: number, height: number}>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setPage(0);
    setHasMore(true);
    fetchFiles(currentFolderId, 0);
    if (activeTab === 'albums' && currentFolderId === null) {
      fetchFolders();
    }
    // Also fetch folders if we need them for the Move modal
    if (folders.length === 0) fetchFolders();
  }, [currentFolderId, activeTab]);

  useEffect(() => {
    if (page > 0) {
      fetchFiles(currentFolderId, page);
    }
  }, [page]);

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimer: number | ReturnType<typeof setTimeout>;

    const connectWs = () => {
      const wsUrl = import.meta.env.VITE_WS_URL || (window.location.protocol === 'https:' ? `wss://${window.location.hostname}/api/v1/ws` : `ws://${window.location.hostname}:8000/api/v1/ws`);
      ws = new WebSocket(`${wsUrl}/${token}`);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "FILE_UPLOADED") {
          setPage(0);
          fetchFiles(currentFolderId, 0);
        }
      };

      ws.onclose = () => {
        reconnectTimer = setTimeout(connectWs, 3000);
      };
    };

    connectWs();

    return () => {
      
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [token, currentFolderId, fetchFiles]);

  // const fetchFiles = async (folderId: string | null, pageNum: number) => {
  //   try {
  //     if (pageNum === 0) setInitialLoading(true);
  //     const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  //     let url = `${apiUrl}/files/?skip=${pageNum * 50}&limit=50`;
  //     if (folderId && activeTab !== 'favorites') {
  //       url += `&folder_id=${folderId}`;
  //     }
  //     if (activeTab === 'favorites') {
  //       url += `&is_favorite=true`;
  //     }
  //     const response = await fetch(url, {
  //       headers: {
  //         'Authorization': `Bearer ${token}`
  //       }
  //     });
  //     if (response.ok) {
  //       const data = await response.json();
  //       if (data.length < 50) setHasMore(false);
  //       else setHasMore(true);
        
  //       if (pageNum === 0) {
  //         setFiles(data);
  //       } else {
  //         setFiles(prev => [...prev, ...data]);
  //       }
  //     } else if (response.status === 401) {
  //       onLogout();
  //     }
  //   } catch (err) {
  //     console.error("Failed to fetch files", err);
  //   } finally {
  //     if (pageNum === 0) setInitialLoading(false);
  //   }
  // };

  const fetchFiles = useCallback(async (folderId: string | null, pageNum: number) => {
    try {
      if (pageNum === 0) setInitialLoading(true);
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      let url = `${apiUrl}/files/?skip=${pageNum * 50}&limit=50`;
      
      if (folderId && activeTab !== 'favorites') {
        url += `&folder_id=${folderId}`;
      }
      if (activeTab === 'favorites') {
        url += `&is_favorite=true`;
      }

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        
        if (pageNum === 0) {
          setFiles(data);
        } else {
          setFiles(prev => [...prev, ...data]);
        }
        
        setHasMore(data.length === 50);
      } else if (response.status === 401) {
        onLogout();
      }
    } catch (err) {
      console.error("Failed to fetch files", err);
    } finally {
      if (pageNum === 0) setInitialLoading(false);
    }
  }, [activeTab, token, onLogout]);

  const fetchFolders = async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/folders/`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setFolders(data);
      }
    } catch (err) {
      console.error("Failed to fetch folders", err);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await uploadFiles(Array.from(e.dataTransfer.files));
    }
  };

  const compressImage = (file: File): Promise<File> => {
    return new Promise((resolve) => {
      if (!file.type.startsWith('image/')) {
        resolve(file); return;
      }
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = (e) => {
        const img = new Image();
        img.src = e.target?.result as string;
        img.onload = () => {
          const MAX_WIDTH = 1920; const MAX_HEIGHT = 1920;
          let width = img.width; let height = img.height;
          if (width > height) {
            if (width > MAX_WIDTH) { height = Math.round((height *= MAX_WIDTH / width)); width = MAX_WIDTH; }
          } else {
            if (height > MAX_HEIGHT) { width = Math.round((width *= MAX_HEIGHT / height)); height = MAX_HEIGHT; }
          }
          const canvas = document.createElement('canvas');
          canvas.width = width; canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx?.drawImage(img, 0, 0, width, height);
          canvas.toBlob((blob) => {
            if (blob) {
              resolve(new File([blob], file.name, { type: 'image/jpeg', lastModified: Date.now() }));
            } else { resolve(file); }
          }, 'image/jpeg', 0.85);
        };
        img.onerror = () => resolve(file);
      };
      reader.onerror = () => resolve(file);
    });
  };

  const uploadFiles = async (fileList: File[]) => {
    setUploading(true);
    setUploadProgress(0);
    
    const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
    let totalLoaded = 0;
    
    const compressedFiles = await Promise.all(fileList.map(f => compressImage(f)));
    const totalSize = compressedFiles.reduce((acc, file) => acc + file.size, 0);

    for (let i = 0; i < compressedFiles.length; i++) {
      const file = compressedFiles[i];
      const formData = new FormData();
      formData.append("files", file);
      
      try {
        const exifData = await exifr.parse(file, { pick: ['DateTimeOriginal'] });
        if (exifData && exifData.DateTimeOriginal) {
          formData.append("date_taken", exifData.DateTimeOriginal.toISOString());
        }
      } catch (e) {
        // silently ignore EXIF parsing errors
      }

      if (currentFolderId) {
        formData.append("folder_id", currentFolderId);
      }

      await new Promise<void>((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${apiUrl}/files/`);
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const currentTotalLoaded = totalLoaded + event.loaded;
            const percentComplete = Math.round((currentTotalLoaded / totalSize) * 100);
            setUploadProgress(Math.min(percentComplete, 100));
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            totalLoaded += file.size;
            resolve();
          } else {
            console.error(`Upload failed for ${file.name} with status`, xhr.status);
            resolve(); 
          }
        };

        xhr.onerror = () => {
          console.error(`Upload failed for ${file.name} due to network error`);
          resolve(); 
        };

        xhr.send(formData);
      });
    }

    setPage(0);
    await fetchFiles(currentFolderId, 0);
    setUploading(false);
    setUploadProgress(null);
  };

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFolderName.trim()) return;
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/folders/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newFolderName.trim() })
      });
      if (response.ok) {
        setNewFolderName('');
        setShowCreateModal(false);
        fetchFolders();
      } else {
        const errorText = await response.text();
        alert(`Failed to create album: ${response.status} - ${errorText}`);
      }
    } catch (err: any) {
      console.error("Failed to create folder", err);
      alert(`Network error: ${err.message}`);
    }
  };

  const handleDeleteFolder = async (e: React.MouseEvent, folderId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Delete this album? Photos inside will be moved to 'All Photos'.")) return;
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/folders/${folderId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        setFolders(prev => prev.filter(f => f.id !== folderId));
      }
    } catch (err) {
      console.error("Failed to delete folder", err);
    }
  };

  const handleMoveFile = async (fileId: string, targetFolderId: string | null) => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      
      if (fileId === 'BULK') {
        const response = await fetch(`${apiUrl}/files/bulk/move`, {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_ids: Array.from(selectedFileIds), folder_id: targetFolderId })
        });
        if (response.ok) {
          setFiles(prev => prev.filter(f => !selectedFileIds.has(f.id)));
          setMovingFileId(null);
          setIsSelectMode(false);
          setSelectedFileIds(new Set());
        }
      } else {
        const response = await fetch(`${apiUrl}/files/${fileId}/move`, {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder_id: targetFolderId })
        });
        if (response.ok) {
          setFiles(prev => prev.filter(f => f.id !== fileId));
          setMovingFileId(null);
        } else {
          alert("Failed to move file.");
        }
      }
    } catch (err) {
      console.error("Failed to move file", err);
    }
  };

  const toggleFavorite = async (fileId: string) => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/files/${fileId}/favorite`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        if (activeTab === 'favorites' && !data.is_favorite) {
          setFiles(prev => prev.filter(f => f.id !== fileId));
        } else {
          setFiles(prev => prev.map(f => f.id === fileId ? { ...f, is_favorite: data.is_favorite } : f));
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/auth/change-password`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password: passwordForm.old, new_password: passwordForm.new })
      });
      if (response.ok) {
        alert("Password changed successfully!");
        setShowPasswordModal(false);
        setPasswordForm({ old: '', new: '' });
      } else {
        alert("Incorrect old password or failed to change.");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const toggleSelection = (fileId: string) => {
    const newSet = new Set(selectedFileIds);
    if (newSet.has(fileId)) newSet.delete(fileId);
    else newSet.add(fileId);
    setSelectedFileIds(newSet);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    await uploadFiles(Array.from(e.target.files));
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDeleteAccount = async () => {
    if (!window.confirm("WARNING: This will permanently delete your account and ALL your photos. This action cannot be undone. Are you absolutely sure?")) return;
    
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/auth/me`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        onLogout();
      } else {
        alert("Failed to delete account.");
      }
    } catch (err) {
      console.error("Delete account failed", err);
    }
  };

  const handleDownload = async (e: React.MouseEvent, fileId: string, originalName: string) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/files/download/${fileId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = originalName;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        alert("Failed to download file: Server returned " + response.status);
      }
    } catch (err) {
      console.error("Download failed", err);
      alert("Download failed due to network error.");
    }
  };

  const handleDelete = async (e: React.MouseEvent, fileId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this photo?")) return;
    
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const response = await fetch(`${apiUrl}/files/${fileId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        setFiles(prev => prev.filter(f => f.id !== fileId));
      } else {
        alert("Failed to delete file.");
      }
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement, Event>, fileId: string) => {
    const target = e.target as HTMLImageElement;
    if (target.naturalWidth && target.naturalHeight) {
      setDimensions(prev => {
        if (prev[fileId]?.width === target.naturalWidth && prev[fileId]?.height === target.naturalHeight) {
          return prev;
        }
        return {
          ...prev,
          [fileId]: { width: target.naturalWidth, height: target.naturalHeight }
        };
      });
    }
  };

  return (
    <div 
      className="min-h-screen mesh-bg text-white relative overflow-hidden font-sans"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center border-4 border-dashed border-white/50 m-4 rounded-3xl pointer-events-none transition-all duration-300">
          <div className="text-3xl font-bold text-white flex flex-col items-center">
            <svg className="w-20 h-20 mb-4 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Drop photos here to upload
          </div>
        </div>
      )}
      <div className="relative z-10 max-w-[1400px] mx-auto px-4 py-8">
        {/* Header */}
        <header className="flex flex-col sm:flex-row justify-between items-center gap-4 sm:gap-0 mb-6 sm:mb-10 glass-panel p-4 sm:p-3 sm:px-6 rounded-[2rem] sm:rounded-full animate-fade-in-up">
          <div className="flex items-center space-x-2 sm:space-x-3 w-full sm:w-auto justify-center sm:justify-start">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center border border-white/20 shrink-0">
              <svg className="w-4 h-4 sm:w-5 sm:h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Gallery</h1>
          </div>
          
          <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-4 w-full sm:w-auto">
            <label className="premium-btn cursor-pointer inline-flex items-center space-x-1 sm:space-x-2 !px-3 sm:!px-6 !py-1.5 sm:!py-2.5">
              <svg className="w-4 h-4 sm:w-5 sm:h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <span className="text-sm sm:text-base whitespace-nowrap">{uploading ? '...' : 'Upload'}</span>
              <input 
                type="file" 
                multiple 
                className="hidden" 
                ref={fileInputRef}
                onChange={handleUpload}
                disabled={uploading}
              />
            </label>
            <button 
              onClick={() => { setIsSelectMode(!isSelectMode); setSelectedFileIds(new Set()); }}
              className="premium-btn text-xs sm:text-sm !px-3 sm:!px-5 !py-1.5 sm:!py-2.5 !bg-blue-500/20 hover:!bg-blue-500/40 text-blue-200 border border-blue-500/30 whitespace-nowrap flex-1 justify-center sm:flex-none"
            >
              {isSelectMode ? 'Cancel' : 'Select'}
            </button>
            <button 
              onClick={() => setShowSettingsModal(true)}
              className="premium-btn !px-3 sm:!px-4 !py-1.5 sm:!py-2.5 !bg-white/10 hover:!bg-white/20 whitespace-nowrap flex items-center justify-center shrink-0"
              title="Settings"
            >
              <svg className="w-5 h-5 text-white/80" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
            </button>
          </div>
          
          {/* Tabs */}
          <div className="flex bg-black/40 backdrop-blur-xl rounded-full p-1 border border-white/10 sm:mx-0 mx-auto w-full sm:w-auto overflow-hidden">
            <button 
              onClick={() => { setActiveTab('photos'); setCurrentFolderId(null); }}
              className={`flex-1 sm:flex-none px-4 py-2 rounded-full text-sm font-semibold transition-all ${activeTab === 'photos' && currentFolderId === null ? 'bg-white text-black shadow-lg' : 'text-white/60 hover:text-white hover:bg-white/5'}`}
            >
              All Photos
            </button>
            <button 
              onClick={() => setActiveTab('albums')}
              className={`flex-1 sm:flex-none px-4 py-2 rounded-full text-sm font-semibold transition-all ${activeTab === 'albums' ? 'bg-white text-black shadow-lg' : 'text-white/60 hover:text-white hover:bg-white/5'}`}
            >
              Albums
            </button>
            <button 
              onClick={() => { setActiveTab('favorites'); setCurrentFolderId(null); }}
              className={`flex-1 sm:flex-none px-4 py-2 rounded-full text-sm font-semibold transition-all flex items-center justify-center gap-1 ${activeTab === 'favorites' ? 'bg-white text-black shadow-lg' : 'text-white/60 hover:text-white hover:bg-white/5'}`}
            >
              <svg className="w-4 h-4 text-red-500" fill={activeTab === 'favorites' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"></path></svg>
              <span className="hidden sm:inline">Favorites</span>
            </button>
          </div>
        </header>

        {/* Folder Header */}
        {currentFolderId && (
          <div className="flex items-center space-x-4 mb-6 animate-fade-in-up">
            <button 
              onClick={() => setCurrentFolderId(null)}
              className="bg-white/20 hover:bg-white/30 p-2 rounded-full backdrop-blur-md transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
            </button>
            <h2 className="text-2xl font-bold">
              {folders.find(f => f.id === currentFolderId)?.name || 'Album'}
            </h2>
          </div>
        )}

        {/* Progress Bar */}
        {uploadProgress !== null && (
          <div className="w-full bg-white/10 rounded-full h-1.5 mb-6 overflow-hidden">
            <div 
              className="bg-blue-400 h-1.5 rounded-full transition-all duration-300 relative" 
              style={{ width: `${uploadProgress}%` }}
            >
              <div className="absolute inset-0 bg-white/30 animate-pulse"></div>
            </div>
          </div>
        )}

        {/* Folders Grid */}
        {activeTab === 'albums' && !currentFolderId && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6 animate-fade-in-up">
            <button 
              onClick={() => setShowCreateModal(true)}
              className="aspect-square glass-panel rounded-[28px] border-2 border-dashed border-white/30 flex flex-col items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-all cursor-pointer group"
            >
              <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
              </div>
              <span className="font-semibold">New Album</span>
            </button>
            
            {folders.map((folder, idx) => (
              <div 
                key={folder.id} 
                onClick={() => setCurrentFolderId(folder.id)}
                className="aspect-square glass-panel rounded-[28px] flex flex-col relative overflow-hidden group cursor-pointer hover:scale-[1.02] transition-transform duration-300"
                style={{ animationDelay: `${(idx % 10) * 0.05}s` }}
              >
                <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-black/40 z-10 transition-opacity opacity-60 group-hover:opacity-40"></div>
                
                {folder.cover_url ? (
                  <img src={folder.cover_url} alt="Cover" className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:scale-105 transition-transform duration-700" />
                ) : (
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 opacity-20 group-hover:opacity-30 transition-opacity z-0">
                    <svg className="w-24 h-24" fill="currentColor" viewBox="0 0 20 20"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" /></svg>
                  </div>
                )}
                
                <button 
                  onClick={(e) => handleDeleteFolder(e, folder.id)}
                  className="absolute top-3 right-3 z-20 bg-red-500/20 text-red-300 p-2 rounded-full opacity-0 group-hover:opacity-100 hover:bg-red-500 hover:text-white transition-all backdrop-blur-md"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
                
                <div className="mt-auto p-4 z-20 w-full flex justify-between items-end">
                  <span className="font-bold text-lg truncate w-full shadow-black drop-shadow-md">{folder.name}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Files Grid */}
        {(activeTab === 'photos' || activeTab === 'favorites' || currentFolderId) && (
          <PhotoSwipeGallery>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
              
              {initialLoading && Array.from({ length: 12 }).map((_, i) => (
                <div 
                  key={`skeleton-${i}`} 
                  className="aspect-square glass-panel rounded-[28px] relative overflow-hidden animate-pulse bg-white/5"
                  style={{ animationDelay: `${(i % 10) * 0.1}s` }}
                >
                  <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/10 to-transparent -translate-x-full animate-[shimmer_2s_infinite]"></div>
                </div>
              ))}

              {!initialLoading && files.length === 0 && (
                <div className="col-span-full py-20 flex flex-col items-center justify-center text-slate-500">
                  <svg className="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <p className="text-lg">No files yet. Upload some photos!</p>
                </div>
              )}
              
              {!initialLoading && files.map((file, idx) => {
                const isImage = file.mime_type && file.mime_type.startsWith('image/');
                const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
                const baseUrl = apiUrl.replace('/api/v1', '');
                
                const fileUrl = (file.storage_path || '').startsWith('http') 
                  ? (file.storage_path || '')
                  : `${baseUrl}${(file.storage_path || '').replace('..', '')}`;
                  
                const previewUrl = isImage ? (file.preview_url || fileUrl) : fileUrl;
                const thumbnailUrl = isImage ? (file.thumbnail_url || fileUrl) : fileUrl;
                const dim = dimensions[file.id] || { width: 1024, height: 768 }; 
                
                return (
                  <div 
                    key={file.id} 
                    className="group aspect-square glass-panel rounded-[28px] flex flex-col items-center justify-center relative transition-all duration-500 hover:scale-[1.02] cursor-pointer overflow-hidden animate-fade-in-up"
                    style={{ animationDelay: `${(idx % 10) * 0.05}s` }}
                  >
                    {isImage ? (
                      <Item
                        original={previewUrl}
                        thumbnail={thumbnailUrl}
                        width={dim.width > 2048 ? 2048 : dim.width}
                        height={dim.width > 2048 ? Math.round((dim.height / dim.width) * 2048) : dim.height}
                      >
                        {({ ref, open }) => (
                          <div className="relative w-full h-full">
                            <img 
                              ref={ref as any} 
                              onClick={isSelectMode ? (e) => { e.stopPropagation(); toggleSelection(file.id); } : open} 
                              onLoad={(e) => handleImageLoad(e, file.id)}
                              src={thumbnailUrl} 
                              alt={file.original_name} 
                              className={`absolute inset-0 w-full h-full object-cover transition-all ${isSelectMode && selectedFileIds.has(file.id) ? 'scale-90 rounded-2xl opacity-70' : 'opacity-90 group-hover:opacity-100'}`}
                              loading="lazy"
                              onError={(e) => { (e.target as HTMLImageElement).src = fileUrl; }}
                            />
                            {/* Favorite Button Overlay */}
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleFavorite(file.id); }}
                              className={`absolute top-2 left-2 p-1.5 rounded-full backdrop-blur-md transition-all duration-300 z-30 ${file.is_favorite ? 'opacity-100 bg-white/20' : 'opacity-100 sm:opacity-0 group-hover:opacity-100 bg-black/20 hover:bg-black/40'}`}
                            >
                              <svg className={`w-5 h-5 ${file.is_favorite ? 'text-red-500' : 'text-white/80'}`} fill={file.is_favorite ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"></path></svg>
                            </button>
                            
                            {isSelectMode && (
                              <div className="absolute bottom-2 right-2 w-6 h-6 rounded-full border-2 border-white flex items-center justify-center transition-all bg-black/40 z-20 pointer-events-none">
                                {selectedFileIds.has(file.id) && <div className="w-3.5 h-3.5 bg-blue-500 rounded-full" />}
                              </div>
                            )}
                          </div>
                        )}
                      </Item>
                    ) : (
                      <>
                        <div className={`absolute inset-0 transition-all ${isSelectMode && selectedFileIds.has(file.id) ? 'bg-blue-500/20 scale-90 rounded-2xl' : 'bg-white/5 opacity-50 group-hover:opacity-100'}`} 
                             onClick={isSelectMode ? () => toggleSelection(file.id) : undefined}
                        />
                        <div className="relative z-10 flex flex-col items-center p-4 w-full h-full justify-between pointer-events-none">
                          <div className="flex-1 flex items-center justify-center">
                            <span className="text-5xl filter drop-shadow-md group-hover:scale-110 transition-transform duration-500">
                              {file.original_name.endsWith('.pdf') ? '📄' : '📁'}
                            </span>
                          </div>
                        </div>
                        {isSelectMode && (
                          <div className="absolute bottom-2 right-2 w-6 h-6 rounded-full border-2 border-white flex items-center justify-center transition-all bg-black/40 z-20 pointer-events-none">
                            {selectedFileIds.has(file.id) && <div className="w-3.5 h-3.5 bg-blue-500 rounded-full" />}
                          </div>
                        )}
                      </>
                    )}
                    
                    <button 
                      onClick={(e) => handleDelete(e, file.id)}
                      className="absolute top-3 right-14 bg-red-500/10 dark:bg-black/30 backdrop-blur-xl text-red-500 dark:text-red-400 p-2.5 rounded-full opacity-100 sm:opacity-0 group-hover:opacity-100 transition-all duration-300 z-30 pointer-events-auto flex items-center justify-center cursor-pointer border border-red-500/30 hover:bg-red-500 hover:text-white hover:border-red-400 shadow-[0_4px_12px_rgba(239,68,68,0.2)] active:scale-90"
                      title="Delete Photo"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
  
                    <button 
                      onClick={(e) => handleDownload(e, file.id, file.original_name)}
                      className="absolute top-3 right-3 bg-white/20 dark:bg-black/30 backdrop-blur-xl text-slate-800 dark:text-white p-2.5 rounded-full opacity-100 sm:opacity-0 group-hover:opacity-100 transition-all duration-300 z-30 pointer-events-auto flex items-center justify-center cursor-pointer border border-white/40 dark:border-white/20 hover:bg-white/40 dark:hover:bg-white/20 hover:scale-105 active:scale-90 shadow-[0_4px_12px_rgba(0,0,0,0.1)]"
                      title="Download Original"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    </button>
                    
                    <div className="absolute bottom-3 left-3 right-3 bg-black/40 backdrop-blur-xl p-2 rounded-2xl translate-y-4 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all duration-500 z-20 pointer-events-none border border-white/10">
                      <p className="text-xs truncate w-full text-center font-medium text-white/90" title={file.original_name}>
                        {file.original_name}
                      </p>
                    </div>

                    {/* Move Button */}
                    <button 
                      onClick={(e) => { e.stopPropagation(); setMovingFileId(file.id); }}
                      className="absolute top-3 right-24 bg-blue-500/10 dark:bg-black/30 backdrop-blur-xl text-blue-500 dark:text-blue-400 p-2.5 rounded-full opacity-100 sm:opacity-0 group-hover:opacity-100 transition-all duration-300 z-30 pointer-events-auto flex items-center justify-center cursor-pointer border border-blue-500/30 hover:bg-blue-500 hover:text-white hover:border-blue-400 shadow-[0_4px_12px_rgba(59,130,246,0.2)] active:scale-90"
                      title="Move to Album"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 7v8a2 2 0 002 2h6M8 7l-2 2m2-2l2 2m4-4h.01M16 11h.01M16 15h.01M16 19h.01" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
            
            {!initialLoading && files.length > 0 && hasMore && (
              <div className="w-full flex justify-center mt-10 pb-8">
                <button 
                  onClick={() => setPage(p => p + 1)}
                  className="premium-btn !px-8 !py-3 font-semibold shadow-xl"
                >
                  Load More
                </button>
              </div>
            )}
          </PhotoSwipeGallery>
        )}
      </div>

      {/* Move File Modal */}
      {movingFileId && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in-up">
          <div className="bg-slate-900/90 border border-white/20 p-6 rounded-3xl w-full max-w-sm shadow-2xl backdrop-blur-2xl">
            <h3 className="text-xl font-bold mb-4 text-white">Move Photo to Album</h3>
            <div className="max-h-60 overflow-y-auto space-y-2 mb-6">
              {currentFolderId && (
                <button
                  onClick={() => handleMoveFile(movingFileId, null)}
                  className="w-full text-left px-4 py-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors text-white font-medium"
                >
                  📁 All Photos (Root)
                </button>
              )}
              {folders.filter(f => f.id !== currentFolderId).map(folder => (
                <button
                  key={folder.id}
                  onClick={() => handleMoveFile(movingFileId, folder.id)}
                  className="w-full text-left px-4 py-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors text-white font-medium"
                >
                  📁 {folder.name}
                </button>
              ))}
              {folders.length === 0 && !currentFolderId && (
                <p className="text-white/50 text-center py-4">No albums created yet.</p>
              )}
            </div>
            <button 
              onClick={() => setMovingFileId(null)}
              className="w-full py-2.5 rounded-full bg-white/10 hover:bg-white/20 font-semibold transition-colors text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Create Folder Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in-up">
          <div className="bg-slate-900/90 border border-white/20 p-6 rounded-3xl w-full max-w-sm shadow-2xl backdrop-blur-2xl">
            <h3 className="text-xl font-bold mb-4">Create New Album</h3>
            <form onSubmit={handleCreateFolder}>
              <input 
                type="text" 
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                placeholder="e.g. Summer Vacation"
                className="premium-input mb-6 w-full"
                autoFocus
              />
              <div className="flex space-x-3">
                <button 
                  type="button" 
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 py-2.5 rounded-full bg-white/10 hover:bg-white/20 font-semibold transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={!newFolderName.trim()}
                  className="flex-1 py-2.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors disabled:opacity-50"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in-up">
          <div className="bg-slate-900/90 border border-white/20 p-6 rounded-3xl w-full max-w-sm shadow-2xl backdrop-blur-2xl">
            <h3 className="text-xl font-bold mb-4 text-white">Change Password</h3>
            <form onSubmit={handleChangePassword}>
              <input 
                type="password" 
                value={passwordForm.old}
                onChange={e => setPasswordForm({...passwordForm, old: e.target.value})}
                placeholder="Current Password"
                className="premium-input mb-4 w-full"
                required
              />
              <input 
                type="password" 
                value={passwordForm.new}
                onChange={e => setPasswordForm({...passwordForm, new: e.target.value})}
                placeholder="New Password"
                className="premium-input mb-6 w-full"
                required
              />
              <div className="flex space-x-3">
                <button type="button" onClick={() => setShowPasswordModal(false)} className="flex-1 py-2.5 rounded-full bg-white/10 hover:bg-white/20 font-semibold transition-colors text-white">Cancel</button>
                <button type="submit" disabled={!passwordForm.old || !passwordForm.new} className="flex-1 py-2.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors disabled:opacity-50">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in-up">
          <div className="bg-slate-900/90 border border-white/20 p-6 rounded-3xl w-full max-w-sm shadow-2xl backdrop-blur-2xl">
            <h3 className="text-xl font-bold mb-6 text-white text-center">Settings</h3>
            <div className="space-y-3">
              <button 
                onClick={() => { setShowSettingsModal(false); setShowPasswordModal(true); }}
                className="w-full py-3 px-4 rounded-xl bg-white/5 hover:bg-white/10 font-medium transition-colors text-white flex items-center justify-between"
              >
                <span>Change Password</span>
                <svg className="w-5 h-5 text-white/50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
              </button>
              
              <button 
                onClick={onLogout} 
                className="w-full py-3 px-4 rounded-xl bg-white/5 hover:bg-white/10 font-medium transition-colors text-white flex items-center justify-between"
              >
                <span>Log Out</span>
                <svg className="w-5 h-5 text-white/50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
              </button>

              <button 
                onClick={handleDeleteAccount} 
                className="w-full py-3 px-4 rounded-xl bg-red-500/10 hover:bg-red-500/20 font-medium transition-colors text-red-400 flex items-center justify-between border border-red-500/20"
              >
                <span>Delete Account</span>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
              </button>
            </div>
            <button 
              onClick={() => setShowSettingsModal(false)}
              className="w-full mt-6 py-2.5 rounded-full bg-white/10 hover:bg-white/20 font-semibold transition-colors text-white"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Floating Bulk Action Bar */}
      {isSelectMode && selectedFileIds.size > 0 && (
        <div className="fixed bottom-6 left-4 right-4 sm:bottom-10 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-50 glass-panel p-3 sm:p-4 rounded-2xl sm:rounded-full flex items-center justify-between sm:justify-start gap-4 animate-fade-in-up shadow-2xl border border-white/20">
          <span className="font-bold text-white/90 pl-2 whitespace-nowrap text-sm sm:text-base">{selectedFileIds.size} Selected</span>
          <button onClick={() => setMovingFileId('BULK')} className="premium-btn !py-2 !px-4 sm:!py-2.5 sm:!px-6 !bg-blue-500/80 hover:!bg-blue-500 !text-white shadow-lg whitespace-nowrap text-sm sm:text-base">
            Move To Album
          </button>
        </div>
      )}
    </div>
  );
};

export default Gallery;

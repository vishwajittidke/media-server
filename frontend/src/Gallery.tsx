import React, { useEffect, useState, useRef } from 'react';
import { Gallery as PhotoSwipeGallery, Item } from 'react-photoswipe-gallery';
import 'photoswipe/dist/photoswipe.css';

interface FileItem {
  id: string;
  original_name: string;
  stored_name: string;
  mime_type: string;
  created_at: string;
  storage_path?: string;
  thumbnail_url?: string;
  preview_url?: string;
}

interface GalleryProps {
  token: string;
  onLogout: () => void;
}

const Gallery: React.FC<GalleryProps> = ({ token, onLogout }) => {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [dimensions, setDimensions] = useState<Record<string, {width: number, height: number}>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchFiles();

    let ws: WebSocket;
    let reconnectTimer: NodeJS.Timeout;

    const connectWs = () => {
      const wsUrl = import.meta.env.VITE_WS_URL || (window.location.protocol === 'https:' ? `wss://${window.location.hostname}/api/v1/ws` : `ws://${window.location.hostname}:8000/api/v1/ws`);
      ws = new WebSocket(`${wsUrl}/${token}`);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "FILE_UPLOADED") {
          // Verify it's not already in the state before prepending
          setFiles(prev => prev.some(f => f.id === data.file.id) ? prev : [data.file, ...prev]);
        }
      };

      ws.onclose = () => {
        // Reconnect after 3 seconds if connection drops
        reconnectTimer = setTimeout(connectWs, 3000);
      };
    };

    connectWs();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null; // Prevent reconnect loop on unmount
        ws.close();
      }
    };
  }, [token]);

  const fetchFiles = async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
      const response = await fetch(`${apiUrl}/files/`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setFiles(data);
      } else if (response.status === 401) {
        onLogout();
      }
    } catch (err) {
      console.error("Failed to fetch files", err);
    } finally {
      setInitialLoading(false);
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

  const uploadFiles = async (fileList: File[]) => {
    setUploading(true);
    setUploadProgress(0);
    
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    
    let totalBytesLoaded = 0;
    const totalBytesToUpload = fileList.reduce((acc, file) => acc + file.size, 0);

    // Upload sequentially to avoid Payload Too Large errors (413)
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const formData = new FormData();
      formData.append("files", file);

      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${apiUrl}/files/`);
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        
        // We only track the progress of the CURRENT file and add it to previous files' total
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const currentTotalLoaded = totalBytesLoaded + event.loaded;
            const percentComplete = Math.round((currentTotalLoaded / totalBytesToUpload) * 100);
            setUploadProgress(Math.min(percentComplete, 100));
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            totalBytesLoaded += file.size; // Lock in the file's size upon completion
            resolve();
          } else {
            console.error(`Upload failed for ${file.name} with status`, xhr.status);
            // We resolve instead of reject so one failed file doesn't stop the rest
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

    // After all files are uploaded (or failed), fetch the final list
    await fetchFiles();
    setUploading(false);
    setUploadProgress(null);
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
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
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
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
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
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
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
        // Only update if it's not already set or differs, to prevent infinite loops
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
        <header className="flex flex-row justify-between items-center mb-6 sm:mb-10 glass-panel p-2 px-4 sm:p-3 sm:px-6 rounded-full animate-fade-in-up">
          <div className="flex items-center space-x-2 sm:space-x-3">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center border border-white/20 shrink-0">
              <svg className="w-4 h-4 sm:w-5 sm:h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Gallery</h1>
          </div>
          
          <div className="flex items-center space-x-2 sm:space-x-4">
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
              onClick={handleDeleteAccount} 
              className="premium-btn text-xs sm:text-sm !px-3 sm:!px-5 !py-1.5 sm:!py-2.5 !bg-red-500/20 hover:!bg-red-500/40 text-red-200 border border-red-500/30 whitespace-nowrap"
            >
              Delete Account
            </button>
            <button 
              onClick={onLogout} 
              className="premium-btn text-xs sm:text-sm !px-3 sm:!px-5 !py-1.5 sm:!py-2.5 !bg-white/10 hover:!bg-white/20 whitespace-nowrap"
            >
              Log Out
            </button>
          </div>
        </header>

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

        {/* Grid */}
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
              // Use direct stored URLs since we're using Cloudinary, or fallback to local
              const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
              const baseUrl = apiUrl.replace('/api/v1', '');
              
              const fileUrl = (file.storage_path || '').startsWith('http') 
                ? (file.storage_path || '')
                : `${baseUrl}${(file.storage_path || '').replace('..', '')}`;
                
              // If Cloudinary succeeded, it has a preview_url. If it failed to local, 
              // Pillow might have failed to generate the preview, so we use fileUrl as a bulletproof fallback.
              const previewUrl = isImage ? (file.preview_url || fileUrl) : fileUrl;
              const thumbnailUrl = isImage ? (file.thumbnail_url || fileUrl) : fileUrl;
              const dim = dimensions[file.id] || { width: 1024, height: 768 }; // Temporary fallback until loaded
              
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
                        <img 
                          ref={ref as any} 
                          onClick={open} 
                          onLoad={(e) => handleImageLoad(e, file.id)}
                          src={thumbnailUrl} 
                          alt={file.original_name} 
                          className="absolute inset-0 w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity"
                          loading="lazy"
                          onError={(e) => {
                            // Fallback to original if thumbnail doesn't exist (e.g. older uploads)
                            (e.target as HTMLImageElement).src = fileUrl;
                          }}
                        />
                      )}
                    </Item>
                  ) : (
                    <>
                      <div className="absolute inset-0 bg-white/5 opacity-50 group-hover:opacity-100 transition-opacity" />
                      <div className="relative z-10 flex flex-col items-center p-4 w-full h-full justify-between">
                        <div className="flex-1 flex items-center justify-center">
                          <span className="text-5xl filter drop-shadow-md group-hover:scale-110 transition-transform duration-500">
                            {file.original_name.endsWith('.pdf') ? '📄' : '📁'}
                          </span>
                        </div>
                      </div>
                    </>
                  )}
                  
                  {/* iPhone 17 Themed Delete Button */}
                  <button 
                    onClick={(e) => handleDelete(e, file.id)}
                    className="absolute top-3 right-14 bg-red-500/10 dark:bg-black/30 backdrop-blur-xl text-red-500 dark:text-red-400 p-2.5 rounded-full opacity-100 sm:opacity-0 group-hover:opacity-100 transition-all duration-300 z-30 pointer-events-auto flex items-center justify-center cursor-pointer border border-red-500/30 hover:bg-red-500 hover:text-white hover:border-red-400 shadow-[0_4px_12px_rgba(239,68,68,0.2)] active:scale-90"
                    title="Delete Photo"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>

                  {/* Download Button */}
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
                </div>
              );
            })}
          </div>
        </PhotoSwipeGallery>
      </div>
    </div>
  );
};

export default Gallery;

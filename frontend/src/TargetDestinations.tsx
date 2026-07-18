import React, { useState, useEffect } from 'react';

interface Target {
  id: string;
  provider_type: 'AWS_S3' | 'GOOGLE_DRIVE' | 'CLOUDINARY' | 'SUPABASE';
  connection_name: string;
  is_active: boolean;
  created_at: string;
}

interface TargetDestinationsProps {
  onClose: () => void;
  token: string;
}

export function TargetDestinations({ onClose, token }: TargetDestinationsProps) {
  const [targets, setTargets] = useState<Target[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'list' | 'edit'>('list');
  const [editingTarget, setEditingTarget] = useState<Partial<Target> | null>(null);
  const [formData, setFormData] = useState<any>({});

  const fetchTargets = async () => {
    setLoading(true);
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const res = await fetch(`${apiUrl}/targets/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTargets(data);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchTargets();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    // Implementation for saving target (POST or PUT)
    const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
    const url = editingTarget?.id 
      ? `${apiUrl}/targets/${editingTarget.id}`
      : `${apiUrl}/targets/`;
    
    const method = editingTarget?.id ? 'PUT' : 'POST';

    try {
      const res = await fetch(url, {
        method,
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({
          provider_type: formData.provider_type,
          connection_name: formData.connection_name,
          is_active: formData.is_active ?? true,
          credentials: formData.credentials
        })
      });
      
      if (res.ok) {
        await fetchTargets();
        setActiveTab('list');
      } else {
        alert("Failed to save target");
      }
    } catch (e) {
      console.error(e);
      alert("Error saving target");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this target?")) return;
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';
      const res = await fetch(`${apiUrl}/targets/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchTargets();
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-md animate-fade-in-up">
      <div className="bg-slate-900 border border-white/10 rounded-[32px] w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden shadow-2xl">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10 bg-white/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center text-blue-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
            </div>
            <h2 className="text-2xl font-bold text-white">Target Destinations</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-white/10 text-white/60 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <div className="w-1/3 border-r border-white/10 flex flex-col bg-slate-900/50">
            <div className="p-4 flex justify-between items-center border-b border-white/5">
              <h3 className="text-lg font-semibold text-white/90">Saved Targets</h3>
              <button 
                onClick={() => {
                  setEditingTarget({});
                  setFormData({ provider_type: 'AWS_S3' });
                  setActiveTab('edit');
                }}
                className="px-4 py-2 text-sm font-medium bg-blue-500 hover:bg-blue-600 text-white rounded-full transition-colors"
              >
                New Target
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loading ? (
                <div className="text-center text-white/50 py-4">Loading targets...</div>
              ) : targets.length === 0 ? (
                <div className="text-center text-white/40 py-8 text-sm">No targets configured yet.</div>
              ) : (
                targets.map(t => (
                  <div 
                    key={t.id}
                    onClick={() => {
                      setEditingTarget(t);
                      setFormData(t);
                      setActiveTab('edit');
                    }}
                    className={`p-4 rounded-2xl border cursor-pointer transition-all ${editingTarget?.id === t.id ? 'bg-blue-500/10 border-blue-500/30' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-semibold text-white">{t.connection_name}</h4>
                      <span className={`text-[10px] uppercase font-bold px-2 py-1 rounded-md ${t.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                        {t.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="text-xs text-white/50 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-white/20"></span>
                      {t.provider_type.replace('_', ' ')}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Main Edit Area */}
          <div className="w-2/3 bg-slate-800/30 p-8 overflow-y-auto">
            {activeTab === 'list' ? (
              <div className="h-full flex flex-col items-center justify-center text-white/40">
                <svg className="w-24 h-24 mb-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                <h3 className="text-xl font-medium text-white/60 mb-2">Select a Target Destination</h3>
                <p className="text-sm text-center max-w-sm">Choose an existing target from the left or click 'New Target' to configure a new integration.</p>
              </div>
            ) : (
              <form onSubmit={handleSave} className="max-w-2xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                  <h3 className="text-2xl font-bold text-white flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                    </div>
                    {editingTarget?.id ? 'Edit Connection Target' : 'New Connection Target'}
                  </h3>
                  {editingTarget?.id && (
                    <div className="flex gap-2">
                      <button type="button" onClick={() => handleDelete(editingTarget.id!)} className="px-4 py-2 text-sm font-medium bg-red-500/20 text-red-400 rounded-full hover:bg-red-500/30 transition-colors">Delete</button>
                    </div>
                  )}
                </div>

                <div className="space-y-6">
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-white/70 mb-2">Connection Name *</label>
                      <input 
                        type="text" 
                        required
                        value={formData.connection_name || ''}
                        onChange={e => setFormData({...formData, connection_name: e.target.value})}
                        className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                        placeholder="e.g. My Backup AWS Bucket"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-white/70 mb-2">Platform Type *</label>
                      <select 
                        value={formData.provider_type || 'AWS_S3'}
                        onChange={e => setFormData({...formData, provider_type: e.target.value, credentials: {}})}
                        className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none transition-all appearance-none"
                        disabled={!!editingTarget?.id}
                      >
                        <option value="AWS_S3">AWS S3 (Amazon Object Storage)</option>
                        <option value="GOOGLE_DRIVE">Google Drive (Workspace)</option>
                        <option value="CLOUDINARY">Cloudinary</option>
                        <option value="SUPABASE">Supabase</option>
                      </select>
                    </div>
                  </div>

                  {/* Dynamic Credentials Form */}
                  <div className="bg-white/5 border border-white/10 p-6 rounded-2xl space-y-5">
                    <h4 className="font-semibold text-white/90 border-b border-white/10 pb-3 mb-5">Authentication Details</h4>
                    
                    {formData.provider_type === 'AWS_S3' && (
                      <>
                        <div className="grid grid-cols-2 gap-6">
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">AWS Region</label>
                            <input 
                              type="text" 
                              value={formData.credentials?.region || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, region: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                              placeholder="us-east-1"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">Bucket Name *</label>
                            <input 
                              type="text" 
                              required={!editingTarget?.id}
                              value={formData.credentials?.bucket || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, bucket: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-6">
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">Access Key ID *</label>
                            <input 
                              type="text" 
                              required={!editingTarget?.id}
                              value={formData.credentials?.access_key || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, access_key: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">Secret Access Key *</label>
                            <input 
                              type="password" 
                              required={!editingTarget?.id}
                              value={formData.credentials?.secret_key || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, secret_key: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                              placeholder={editingTarget?.id ? "(Stored Securely - Leave blank to keep)" : ""}
                            />
                          </div>
                        </div>
                      </>
                    )}

                    {formData.provider_type === 'SUPABASE' && (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-white/70 mb-2">Supabase URL *</label>
                          <input 
                            type="text" 
                            required={!editingTarget?.id}
                            value={formData.credentials?.supabase_url || ''}
                            onChange={e => setFormData({...formData, credentials: {...formData.credentials, supabase_url: e.target.value}})}
                            className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-white/70 mb-2">Service Role Key *</label>
                          <input 
                            type="password" 
                            required={!editingTarget?.id}
                            value={formData.credentials?.supabase_key || ''}
                            onChange={e => setFormData({...formData, credentials: {...formData.credentials, supabase_key: e.target.value}})}
                            className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder={editingTarget?.id ? "(Stored Securely - Leave blank to keep)" : ""}
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-white/70 mb-2">Bucket Name *</label>
                          <input 
                            type="text" 
                            required={!editingTarget?.id}
                            value={formData.credentials?.supabase_bucket || ''}
                            onChange={e => setFormData({...formData, credentials: {...formData.credentials, supabase_bucket: e.target.value}})}
                            className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                          />
                        </div>
                      </>
                    )}
                    
                    {formData.provider_type === 'CLOUDINARY' && (
                      <>
                        <div className="grid grid-cols-2 gap-6">
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">Cloud Name *</label>
                            <input 
                              type="text" 
                              required={!editingTarget?.id}
                              value={formData.credentials?.cloud_name || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, cloud_name: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-white/70 mb-2">API Key *</label>
                            <input 
                              type="text" 
                              required={!editingTarget?.id}
                              value={formData.credentials?.api_key || ''}
                              onChange={e => setFormData({...formData, credentials: {...formData.credentials, api_key: e.target.value}})}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                          </div>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-white/70 mb-2">API Secret *</label>
                          <input 
                            type="password" 
                            required={!editingTarget?.id}
                            value={formData.credentials?.api_secret || ''}
                            onChange={e => setFormData({...formData, credentials: {...formData.credentials, api_secret: e.target.value}})}
                            className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
                            placeholder={editingTarget?.id ? "(Stored Securely - Leave blank to keep)" : ""}
                          />
                        </div>
                      </>
                    )}

                    {formData.provider_type === 'GOOGLE_DRIVE' && (
                      <div className="text-white/60 p-4 border border-blue-500/30 bg-blue-500/5 rounded-xl text-sm">
                        Google Drive integration will use OAuth2 service account credentials. Please paste your entire JSON key file contents below.
                        <textarea 
                          required={!editingTarget?.id}
                          value={formData.credentials?.service_account_json || ''}
                          onChange={e => setFormData({...formData, credentials: {...formData.credentials, service_account_json: e.target.value}})}
                          className="w-full bg-slate-900 border border-white/10 rounded-xl px-4 py-3 mt-4 text-white font-mono text-xs h-32 focus:ring-2 focus:ring-blue-500 outline-none"
                          placeholder={editingTarget?.id ? "(Stored Securely - Leave blank to keep)" : '{"type": "service_account", ...}'}
                        />
                      </div>
                    )}
                  </div>

                  <div className="flex justify-end gap-4 mt-8 pt-6 border-t border-white/10">
                    <button type="button" onClick={() => setActiveTab('list')} className="px-6 py-2.5 rounded-full font-medium text-white/70 hover:bg-white/5 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" className="px-8 py-2.5 rounded-full font-bold bg-blue-500 text-white hover:bg-blue-600 transition-colors shadow-[0_0_20px_rgba(59,130,246,0.4)]">
                      Save Target
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

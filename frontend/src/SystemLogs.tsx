import { useState, useEffect } from 'react';

interface Log {
  id: string;
  level: string;
  category: string;
  message: string;
  stack_trace?: string;
  created_at: string;
}

export default function SystemLogs({ onClose }: { onClose: () => void }) {
  const [logs, setLogs] = useState<Log[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterLevel, setFilterLevel] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [expandedLog, setExpandedLog] = useState<string | null>(null);

  const fetchLogs = async () => {
    setLoading(true);
    const apiUrl = import.meta.env.VITE_API_URL || '/api/v1';
    
    let query = `${apiUrl}/logs/?limit=100`;
    if (filterLevel) query += `&level=${filterLevel}`;
    if (filterCategory) query += `&category=${filterCategory}`;

    try {
      const res = await fetch(query, {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        setLogs(data);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchLogs();
  }, [filterLevel, filterCategory]);

  const getLevelColor = (level: string) => {
    switch(level) {
      case 'ERROR': return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'WARNING': return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
      case 'CRITICAL': return 'text-red-500 bg-red-500/20 border-red-500/30 font-bold';
      case 'SECURITY': return 'text-fuchsia-400 bg-fuchsia-400/10 border-fuchsia-400/20';
      default: return 'text-blue-400 bg-blue-400/10 border-blue-400/20';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-slate-900 w-full max-w-5xl h-[80vh] rounded-3xl border border-white/10 flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-white/10 bg-slate-900/50">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center text-purple-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">System Logs</h2>
              <p className="text-sm text-white/50">Monitor errors, security events, and API bottlenecks</p>
            </div>
          </div>
          
          <div className="flex gap-4 items-center">
            <select 
              value={filterLevel} 
              onChange={e => setFilterLevel(e.target.value)}
              className="bg-slate-800 border border-white/10 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-purple-500/50"
            >
              <option value="">All Levels</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="ERROR">Error</option>
              <option value="SECURITY">Security</option>
              <option value="CRITICAL">Critical</option>
            </select>
            
            <select 
              value={filterCategory} 
              onChange={e => setFilterCategory(e.target.value)}
              className="bg-slate-800 border border-white/10 text-white text-sm rounded-lg px-3 py-2 outline-none focus:border-purple-500/50"
            >
              <option value="">All Categories</option>
              <option value="UPLOAD">Uploads</option>
              <option value="AUTHENTICATION">Authentication</option>
              <option value="DATABASE">Database</option>
              <option value="SYSTEM">System</option>
            </select>

            <button onClick={fetchLogs} className="p-2 bg-slate-800 rounded-lg text-white/70 hover:text-white hover:bg-slate-700 transition">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            </button>
            <button onClick={onClose} className="p-2 bg-white/5 rounded-lg text-white/50 hover:text-white hover:bg-red-500/20 transition">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        {/* Log List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {loading ? (
            <div className="flex justify-center items-center h-full text-white/30">Loading logs...</div>
          ) : logs.length === 0 ? (
            <div className="flex justify-center items-center h-full text-white/30">No logs found.</div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="bg-slate-800/50 border border-white/5 rounded-xl overflow-hidden">
                <div 
                  className="flex items-start gap-4 p-4 cursor-pointer hover:bg-slate-800 transition"
                  onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                >
                  <div className="min-w-[120px] text-xs text-white/40 pt-1 font-mono">
                    {new Date(log.created_at).toLocaleString()}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${getLevelColor(log.level)}`}>
                        {log.level}
                      </span>
                      <span className="text-[10px] text-white/50 font-bold uppercase tracking-wider bg-white/5 px-2 py-0.5 rounded">
                        {log.category}
                      </span>
                    </div>
                    <div className="text-sm text-white/90 font-medium">
                      {log.message}
                    </div>
                  </div>
                  {log.stack_trace && (
                    <div className="text-white/30">
                      <svg className={`w-5 h-5 transition-transform ${expandedLog === log.id ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                    </div>
                  )}
                </div>
                
                {expandedLog === log.id && log.stack_trace && (
                  <div className="p-4 bg-black/40 border-t border-white/5 overflow-x-auto">
                    <pre className="text-[11px] text-red-400/80 font-mono leading-relaxed">
                      {log.stack_trace}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import Gallery from './Gallery';

function App() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [wsToken, setWsToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

  const apiUrl = import.meta.env.VITE_API_URL || 'https://media-server-api.onrender.com/api/v1';

  // On mount, check if we have a valid session cookie
  useEffect(() => {
    const checkSession = async () => {
      try {
        const response = await fetch(`${apiUrl}/auth/check`, {
          credentials: 'include',
        });
        if (response.ok) {
          setIsAuthenticated(true);
        }
      } catch {
        // No valid session — stay on login
      } finally {
        setCheckingSession(false);
      }
    };
    checkSession();
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    try {
      const response = await fetch(`${apiUrl}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        credentials: 'include',  // This tells the browser to accept and store the Set-Cookie
        body: formData.toString()
      });

      if (!response.ok) {
        throw new Error('Invalid credentials');
      }

      const data = await response.json();
      // Store the token ONLY for WebSocket (cookies can't be sent with WS)
      setWsToken(data.access_token);
      setIsAuthenticated(true);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${apiUrl}/auth/logout`, {
        method: "POST",
        credentials: 'include',
      });
    } catch {
      // Even if the API call fails, clear local state
    }
    setIsAuthenticated(false);
    setWsToken(null);
  };

  if (checkingSession) {
    return (
      <div className="min-h-screen flex items-center justify-center mesh-bg">
        <div className="w-8 h-8 rounded-full border-2 border-white/20 border-t-white animate-spin"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Gallery wsToken={wsToken} onLogout={handleLogout} />;
  }

  return (
    <div className="min-h-screen relative flex items-center justify-center overflow-hidden mesh-bg text-slate-100">
      <div className="z-10 w-full max-w-sm px-6 animate-fade-in-up">
        <div className="glass-panel p-8 rounded-[32px] relative overflow-hidden">
          <div className="text-center mb-8 mt-2">
            <h1 className="text-3xl font-bold tracking-tight mb-1">
              Media Server
            </h1>
            <p className="text-white/60 text-sm font-medium">Sign in to your gallery</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-6">
            {error && (
              <div className="bg-red-500/10 border border-red-500/50 text-red-400 p-3 rounded-lg text-sm text-center">
                {error}
              </div>
            )}
            
            <div className="space-y-1">
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="premium-input"
                placeholder="Username"
                required
              />
            </div>
            
            <div className="space-y-1">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="premium-input"
                placeholder="Password"
                required
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="premium-btn w-full mt-4 flex justify-center items-center"
            >
              {isLoading ? (
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              ) : 'Sign In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default App;

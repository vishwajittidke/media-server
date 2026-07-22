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
  const [isColdStart, setIsColdStart] = useState(false);

  const apiUrl = '/api/v1';

  // On mount, check if we have a valid session cookie
  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;
    
    const checkSession = async () => {
      try {
        // If it takes more than 3 seconds, Render is probably waking up from a cold start
        timeoutId = setTimeout(() => setIsColdStart(true), 3000);
        
        const response = await fetch(`${apiUrl}/auth/check`, {
          credentials: 'include',
        });
        if (response.ok) {
          setIsAuthenticated(true);
        }
      } catch {
        // No valid session — stay on login
      } finally {
        clearTimeout(timeoutId);
        setCheckingSession(false);
      }
    };
    checkSession();
    
    return () => clearTimeout(timeoutId);
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
        try {
          const errData = await response.json();
          throw new Error(errData.detail || `Server returned ${response.status}`);
        } catch (e) {
          throw new Error(`Invalid credentials or server error: ${response.status}`);
        }
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
      <div className="min-h-[100dvh] flex flex-col items-center justify-center mesh-bg px-4">
        <div className="w-12 h-12 rounded-full border-4 border-white/10 border-t-blue-500 animate-spin mb-6"></div>
        {isColdStart && (
          <div className="animate-fade-in-up text-center max-w-sm glass-panel p-6 rounded-3xl">
            <h3 className="text-xl font-bold text-white mb-2 tracking-tight">Waking up the server...</h3>
            <p className="text-white/60 text-sm font-medium mb-4">
              Since this is hosted on Render's free tier, the server goes to sleep when inactive. It usually takes about <strong className="text-white">45-50 seconds</strong> to boot up.
            </p>
            <div className="w-full h-1.5 bg-black/40 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '100%', transition: 'width 45s linear', animationDuration: '2s' }} />
            </div>
            <p className="text-white/40 text-xs mt-3">Please don't refresh the page, hang tight!</p>
          </div>
        )}
      </div>
    );
  }

  if (isAuthenticated) {
    return <Gallery wsToken={wsToken} onLogout={handleLogout} />;
  }

  return (
    <div className="min-h-[100dvh] relative flex items-center justify-center overflow-hidden mesh-bg text-slate-100">
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

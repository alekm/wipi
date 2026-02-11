import { createContext, useContext, useState, useEffect } from 'react';

// Mode constants
export const MODE_ADMIN = 'admin';
export const MODE_DEMO = 'demo';

// Create context
const AuthContext = createContext();

// Custom hook to use auth context
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

// Call backend to login
async function loginBackend(password) {
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include', // Important: include cookies
      body: JSON.stringify({ password }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    return data; // { success: true, user: "admin", message: "..." }
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
}

// Call backend to logout
async function logoutBackend() {
  try {
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include', // Important: include cookies
    });

    if (!response.ok) {
      console.warn('Logout request failed, but continuing locally');
    }

    return await response.json();
  } catch (error) {
    console.error('Logout error:', error);
    // Continue with local logout even if backend fails
  }
}

// Check current session status
async function checkSession() {
  try {
    const response = await fetch('/api/auth/me', {
      method: 'GET',
      credentials: 'include', // Important: include cookies
    });

    if (!response.ok) {
      return { authenticated: false, mode: MODE_DEMO };
    }

    const data = await response.json();
    return data; // { authenticated: true/false, user: "admin", mode: "admin"/"demo" }
  } catch (error) {
    console.error('Session check error:', error);
    return { authenticated: false, mode: MODE_DEMO };
  }
}

// Auth provider component
export function AuthProvider({ children }) {
  const [mode, setModeState] = useState(MODE_DEMO);
  const [loading, setLoading] = useState(true);

  // Check session on mount
  useEffect(() => {
    async function restoreSession() {
      const sessionData = await checkSession();
      if (sessionData.authenticated) {
        setModeState(MODE_ADMIN);
      } else {
        setModeState(MODE_DEMO);
      }
      setLoading(false);
    }

    restoreSession();
  }, []);

  // Set mode explicitly (for internal use)
  const setMode = (newMode) => {
    if (newMode === MODE_ADMIN || newMode === MODE_DEMO) {
      setModeState(newMode);
    }
  };

  // Login function - call backend
  const login = async (password) => {
    try {
      const result = await loginBackend(password);
      if (result.success) {
        setModeState(MODE_ADMIN);
        return { success: true };
      } else {
        return { success: false, error: 'Login failed' };
      }
    } catch (error) {
      return { success: false, error: error.message || 'Login failed' };
    }
  };

  // Logout function - call backend
  const logout = async () => {
    await logoutBackend();
    setModeState(MODE_DEMO);
  };

  // Toggle between modes with password protection
  const toggleMode = async () => {
    // If switching from Demo to Admin, require password
    if (mode === MODE_DEMO) {
      const password = prompt('Enter admin password:');
      if (password !== null) {
        // User clicked OK (not cancelled)
        const result = await login(password);
        if (!result.success) {
          alert(result.error || 'Incorrect password');
        }
      }
    } else {
      // Admin to Demo - logout
      await logout();
    }
  };

  // Computed properties
  const isAdmin = mode === MODE_ADMIN;
  const isDemo = mode === MODE_DEMO;

  const value = {
    mode,
    setMode,
    toggleMode,
    login,
    logout,
    isAdmin,
    isDemo,
    loading
  };

  // Show loading state while checking session
  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'var(--color-bg-primary)'
      }}>
        <div style={{ color: 'var(--color-text)' }}>Loading...</div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

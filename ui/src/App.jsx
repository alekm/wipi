import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import PiFleet from './pages/PiFleet';
import Simulation from './pages/Scenarios';
import RuckusOne from './pages/RuckusOne';
import { AuthProvider, useAuth } from './context/AuthContext';
import './index.css';

// Protected route component - redirects to home in demo mode
function ProtectedRoute({ children }) {
  const { isAdmin } = useAuth();

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function Navigation() {
  const location = useLocation();
  const { mode, toggleMode, isAdmin } = useAuth();

  const isActive = (path) => location.pathname === path ? 'active' : '';

  return (
    <header className="header">
      <div className="container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1>WiPi - Wi-Fi Client Farm</h1>
            <p>Orchestrate Raspberry Pi fleet for Wi-Fi load testing</p>
          </div>
          <div className="mode-toggle-container">
            <div className={`mode-badge ${mode}`}>
              <span className="mode-badge-icon"></span>
              {mode.toUpperCase()}
            </div>
            <div className="mode-toggle">
              <span className={`mode-toggle-label ${isAdmin ? 'active' : ''}`}>Admin</span>
              <div
                className={`mode-toggle-switch ${mode}`}
                onClick={toggleMode}
                role="switch"
                aria-checked={!isAdmin}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleMode();
                  }
                }}
              >
                <div className="mode-toggle-slider"></div>
              </div>
              <span className={`mode-toggle-label ${!isAdmin ? 'active' : ''}`}>Demo</span>
            </div>
          </div>
        </div>
        <nav className="nav">
          <Link to="/" className={`nav-link ${isActive('/')}`}>
            Dashboard
          </Link>
          <Link to="/pis" className={`nav-link ${isActive('/pis')}`}>
            Pi Fleet
          </Link>
          {isAdmin && (
            <Link to="/simulation" className={`nav-link ${isActive('/simulation')}`}>
              Simulation
            </Link>
          )}
          <Link to="/ruckus-one" className={`nav-link ${isActive('/ruckus-one')}`}>
            Ruckus One
          </Link>
        </nav>
      </div>
    </header>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Navigation />
        <div className="container">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/pis" element={<PiFleet />} />
            <Route path="/simulation" element={
              <ProtectedRoute>
                <Simulation />
              </ProtectedRoute>
            } />
            <Route path="/ruckus-one" element={<RuckusOne />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

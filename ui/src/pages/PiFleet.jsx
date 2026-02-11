import { useState, useEffect } from 'react';
import { piApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

function PiFleet() {
  const { isAdmin } = useAuth();
  const [pis, setPis] = useState([]);
  const [selectedPi, setSelectedPi] = useState(null);
  const [piStatus, setPiStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPis();
    const interval = setInterval(loadPis, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedPi) {
      loadPiStatus(selectedPi);
    }
  }, [selectedPi]);

  async function loadPis() {
    try {
      const data = await piApi.list();
      // Sort by hostname (case insensitive)
      const sortedData = data.sort((a, b) =>
        a.hostname.toLowerCase().localeCompare(b.hostname.toLowerCase())
      );
      setPis(sortedData);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadPiStatus(piId) {
    try {
      const data = await piApi.getStatus(piId);
      setPiStatus(data);
    } catch (err) {
      console.error('Error loading Pi status:', err);
      setPiStatus(null);
    }
  }

  async function handleDeletePi(piId) {
    if (!confirm(`Are you sure you want to delete Pi "${piId}"?`)) {
      return;
    }

    try {
      await piApi.delete(piId);
      // Clear selected Pi if it was deleted
      if (selectedPi === piId) {
        setSelectedPi(null);
        setPiStatus(null);
      }
      // Reload the list
      await loadPis();
    } catch (err) {
      alert(`Failed to delete Pi: ${err.message}`);
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatUptime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }

  if (loading) {
    return <div className="loading">Loading Pi fleet...</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  return (
    <div className="grid grid-2">
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Registered Pis</h2>
          <div className="badge badge-online">{pis.filter(p => p.status === 'online').length} Online</div>
        </div>

        {pis.length === 0 ? (
          <div className="empty-state">
            <p>No Pis registered yet</p>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
              Deploy an agent to register a Pi
            </p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Hostname</th>
                <th>IP Address</th>
                <th>Status</th>
                <th>Last Seen</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {pis.map(pi => (
                <tr key={pi.pi_id} style={{ background: selectedPi === pi.pi_id ? 'rgba(0, 229, 255, 0.1)' : 'transparent' }}>
                  <td style={{ fontWeight: '500' }}>{pi.hostname}</td>
                  <td>{pi.ip_address}</td>
                  <td>
                    <span className={`badge badge-${pi.status}`}>
                      {pi.status}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {new Date(pi.last_seen).toLocaleTimeString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-primary btn-small"
                      onClick={() => setSelectedPi(pi.pi_id)}
                      style={{ marginRight: '0.5rem' }}
                    >
                      View Details
                    </button>
                    {isAdmin && (
                      <button
                        className="btn btn-danger btn-small"
                        onClick={() => handleDeletePi(pi.pi_id)}
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Pi Details</h2>
        </div>

        {!selectedPi ? (
          <div className="empty-state">Select a Pi to view details</div>
        ) : !piStatus ? (
          <div className="loading">Loading Pi details...</div>
        ) : (
          <div>
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>{piStatus.hostname}</h3>
              <div style={{ color: 'var(--text-secondary)' }}>Agent ID: {piStatus.agent_id}</div>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <h4 style={{ fontSize: '1rem', marginBottom: '0.8rem' }}>System Status</h4>
              <div className="stats">
                <div className="stat">
                  <div className="stat-value">{piStatus.system.cpu_percent.toFixed(1)}%</div>
                  <div className="stat-label">CPU Usage</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{piStatus.system.memory_percent.toFixed(1)}%</div>
                  <div className="stat-label">Memory</div>
                </div>
                {piStatus.system.temperature_celsius && (
                  <div className="stat">
                    <div className="stat-value">{piStatus.system.temperature_celsius.toFixed(1)}°C</div>
                    <div className="stat-label">Temperature</div>
                  </div>
                )}
                <div className="stat">
                  <div className="stat-value">{formatUptime(piStatus.system.uptime_seconds)}</div>
                  <div className="stat-label">Uptime</div>
                </div>
              </div>
            </div>

            <div>
              <h4 style={{ fontSize: '1rem', marginBottom: '0.8rem' }}>
                Interfaces ({piStatus.interfaces.length})
              </h4>

              {piStatus.interfaces.length === 0 ? (
                <div className="empty-state">No active interfaces</div>
              ) : (
                <div className="interface-list">
                  {piStatus.interfaces.map(iface => (
                    <div key={iface.name} className="interface-item">
                      <div>
                        <div className="interface-name">{iface.name}</div>
                        <div className="interface-ip">
                          {iface.ssid && `${iface.ssid} • `}
                          {iface.ip_address || 'No IP'}
                          {iface.signal_strength_dbm && ` • ${iface.signal_strength_dbm} dBm`}
                        </div>
                        {iface.dhcp_personality && (
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.3rem' }}>
                            Personality: <span style={{ textTransform: 'capitalize', fontWeight: '500' }}>
                              {iface.dhcp_personality}
                            </span>
                          </div>
                        )}
                        {iface.traffic && (
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.3rem' }}>
                            Traffic: {iface.traffic.type.replace('_', ' ')} ({iface.traffic.active ? 'active' : 'inactive'})
                          </div>
                        )}
                        {(iface.tx_bytes > 0 || iface.rx_bytes > 0) && (
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.3rem' }}>
                            TX: {formatBytes(iface.tx_bytes)} • RX: {formatBytes(iface.rx_bytes)}
                          </div>
                        )}
                      </div>
                      <span className={`badge badge-${iface.state === 'connected' ? 'online' : 'offline'}`}>
                        {iface.state}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default PiFleet;

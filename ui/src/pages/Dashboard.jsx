import { useState, useEffect } from 'react';
import { monitoringApi, piApi } from '../api/client';

function Dashboard() {
  const [status, setStatus] = useState(null);
  const [pis, setPis] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    try {
      const [statusData, pisData] = await Promise.all([
        monitoringApi.getOverallStatus(),
        piApi.list(),
      ]);

      // Sort Pis by hostname (case insensitive)
      const sortedPis = pisData.sort((a, b) =>
        a.hostname.toLowerCase().localeCompare(b.hostname.toLowerCase())
      );

      setStatus(statusData);
      setPis(sortedPis);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div className="loading">Loading dashboard...</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  const onlinePis = pis.filter(pi => pi.status === 'online').length;
  const totalInterfaces = status?.interfaces?.total || 0;
  const connectedInterfaces = status?.interfaces?.connected || 0;

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">System Overview</h2>
        </div>
        <div className="stats">
          <div className="stat">
            <div className="stat-value">{pis.length}</div>
            <div className="stat-label">Total Pis</div>
          </div>
          <div className="stat">
            <div className="stat-value">{onlinePis}</div>
            <div className="stat-label">Online</div>
          </div>
          <div className="stat">
            <div className="stat-value">{totalInterfaces}</div>
            <div className="stat-label">Total Interfaces</div>
          </div>
          <div className="stat">
            <div className="stat-value">{connectedInterfaces}</div>
            <div className="stat-label">Connected</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Pi Fleet Status</h3>
        </div>
        {pis.length === 0 ? (
          <div className="empty-state">No Pis registered</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Hostname</th>
                <th>IP Address</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {pis.map(pi => (
                <tr key={pi.pi_id}>
                  <td>{pi.hostname}</td>
                  <td>{pi.ip_address}</td>
                  <td>
                    <span className={`badge badge-${pi.status}`}>
                      {pi.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {status?.pis && Object.keys(status.pis).length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Active Interfaces</h3>
          </div>
          <div className="grid grid-3">
            {Object.entries(status.pis).map(([piId, piStatus]) => (
              <div key={piId} style={{ padding: '1rem', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '4px' }}>
                <div style={{ fontWeight: '600', marginBottom: '0.8rem' }}>
                  {piStatus.hostname}
                </div>
                {piStatus.interfaces && piStatus.interfaces.length > 0 ? (
                  <div style={{ fontSize: '0.9rem' }}>
                    {piStatus.interfaces.map(iface => (
                      <div key={iface.name} style={{ marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                        <div style={{ fontWeight: '500' }}>{iface.name}</div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                          {iface.ip_address || 'No IP'} - {iface.state}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No active interfaces</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;

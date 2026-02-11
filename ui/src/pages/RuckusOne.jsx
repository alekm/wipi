import { useState, useEffect } from 'react';
import { ruckusOneApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

function RuckusOne() {
  const { isAdmin, isDemo } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState({
    tenant_id: '',
    client_id: '',
    client_secret: '',
    enabled: true
  });
  const [configSaving, setConfigSaving] = useState(false);
  const [configError, setConfigError] = useState(null);

  const fetchStatus = async () => {
    try {
      const data = await ruckusOneApi.getStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async (e) => {
    e.preventDefault();
    setConfigSaving(true);
    setConfigError(null);
    try {
      await ruckusOneApi.configure(config);
      setShowConfig(false);
      // Refresh status to reflect new configuration
      await fetchStatus();
    } catch (err) {
      setConfigError(err.message);
    } finally {
      setConfigSaving(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    if (autoRefresh) {
      const interval = setInterval(fetchStatus, 10000); // Refresh every 10s
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const getDetectionColor = (correct) => {
    if (correct === null) return '#666';
    return correct ? '#22c55e' : '#ef4444';
  };

  const getDetectionLabel = (correlation) => {
    if (!correlation.r1_detected_os) return 'Not Detected';
    if (correlation.detection_correct) return 'Correct';
    return `Incorrect (${correlation.r1_detected_os})`;
  };

  const renderHeader = () => (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2>Ruckus One Device Detection</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {isAdmin && (
            <button onClick={() => setShowConfig(!showConfig)} className="btn">
              {showConfig ? 'Hide Configuration' : 'Configure Credentials'}
            </button>
          )}
          {!loading && !error && (
            <>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                Auto-refresh
              </label>
              <button onClick={fetchStatus} className="btn">
                Refresh Now
              </button>
            </>
          )}
        </div>
      </div>

      {/* Demo Mode Notice */}
      {isDemo && (
        <div className="alert alert-info" style={{ marginBottom: '2rem' }}>
          Demo mode active - Configuration is read-only. Monitoring and status are available.
        </div>
      )}

      {/* Configuration Panel */}
      {isAdmin && showConfig && (
        <div className="card" style={{ marginBottom: '2rem' }}>
          <h3>Ruckus One API Configuration</h3>
          <form onSubmit={saveConfig} style={{ marginTop: '1rem' }}>
            <div style={{ display: 'grid', gap: '1rem', maxWidth: '600px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Tenant ID
                </label>
                <input
                  type="text"
                  value={config.tenant_id}
                  onChange={(e) => setConfig({ ...config, tenant_id: e.target.value })}
                  placeholder="b21843c8a259439397faa3ef3d663eba"
                  required
                  className="form-input"
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Client ID
                </label>
                <input
                  type="text"
                  value={config.client_id}
                  onChange={(e) => setConfig({ ...config, client_id: e.target.value })}
                  placeholder="05b5e993a03009750c6a736491d45a60"
                  required
                  className="form-input"
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Client Secret
                </label>
                <input
                  type="password"
                  value={config.client_secret}
                  onChange={(e) => setConfig({ ...config, client_secret: e.target.value })}
                  placeholder="••••••••••••••••••••••••••••••••"
                  required
                  className="form-input"
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  id="r1-enabled"
                  checked={config.enabled}
                  onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
                />
                <label htmlFor="r1-enabled">Enable Ruckus One integration</label>
              </div>
            </div>
            {configError && (
              <div className="alert alert-error" style={{ marginTop: '1rem' }}>
                {configError}
              </div>
            )}
            <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
              <button type="submit" className="btn" disabled={configSaving}>
                {configSaving ? 'Saving...' : 'Save Configuration'}
              </button>
              <button type="button" onClick={() => setShowConfig(false)} className="btn" style={{ opacity: 0.7 }}>
                Cancel
              </button>
            </div>
          </form>
          <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(0, 229, 255, 0.05)', border: '1px solid rgba(0, 229, 255, 0.2)', borderRadius: '4px', fontSize: '0.875rem' }}>
            <strong>Note:</strong> Configuration is stored in memory and will be lost on controller restart.
            Get your API credentials from the Ruckus One dashboard under Settings → API.
          </div>
        </div>
      )}
    </>
  );

  if (loading) {
    return (
      <div className="page">
        {renderHeader()}
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        {renderHeader()}
        <div className="alert alert-error">
          {error}
        </div>
        <button onClick={fetchStatus} className="btn">
          Retry
        </button>
      </div>
    );
  }

  const stats = status?.detection_stats || {};
  const correlations = status?.correlations || [];
  const detectionRate = stats.total > 0
    ? ((stats.detected_correctly / stats.total) * 100).toFixed(1)
    : 0;

  return (
    <div className="page">
      {renderHeader()}

      {/* Summary Stats */}
      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3>Detection Summary</h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1.5rem',
          marginTop: '1rem'
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--signal-blue)' }}>
              {stats.total || 0}
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Total Interfaces</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--signal-green)' }}>
              {stats.detected_correctly || 0}
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Detected Correctly</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--signal-red)' }}>
              {stats.detected_incorrectly || 0}
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Detected Incorrectly</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--text-secondary)' }}>
              {stats.not_detected || 0}
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Not Detected</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--signal-orange)' }}>
              {detectionRate}%
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Detection Accuracy</div>
          </div>
        </div>
      </div>

      {/* Per-Personality Breakdown */}
      {Object.keys(stats.by_personality || {}).length > 0 && (
        <div className="card" style={{ marginBottom: '2rem' }}>
          <h3>Detection by Personality</h3>
          <div style={{ marginTop: '1rem' }}>
            {Object.entries(stats.by_personality).map(([personality, personalityStats]) => {
              const accuracy = personalityStats.total > 0
                ? ((personalityStats.detected_correctly / personalityStats.total) * 100).toFixed(1)
                : 0;

              return (
                <div key={personality} style={{
                  marginBottom: '1.5rem',
                  padding: '1rem',
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '8px'
                }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '0.5rem'
                  }}>
                    <h4 style={{ margin: 0, textTransform: 'capitalize' }}>{personality}</h4>
                    <div>
                      <span style={{ fontWeight: 'bold', marginRight: '1rem' }}>
                        {personalityStats.detected_correctly}/{personalityStats.total}
                      </span>
                      <span style={{
                        color: accuracy >= 80 ? 'var(--signal-green)' : accuracy >= 50 ? 'var(--signal-orange)' : 'var(--signal-red)',
                        fontWeight: 'bold'
                      }}>
                        {accuracy}%
                      </span>
                    </div>
                  </div>
                  {Object.keys(personalityStats.detected_as).length > 0 && (
                    <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                      Detected as: {Object.entries(personalityStats.detected_as)
                        .map(([os, count]) => `${os} (${count})`)
                        .join(', ')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Interface Correlations Table */}
      <div className="card">
        <h3>Interface Correlations</h3>
        {correlations.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', marginTop: '1rem' }}>No active interfaces</p>
        ) : (
          <div style={{ overflowX: 'auto', marginTop: '1rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid rgba(255, 255, 255, 0.1)' }}>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Pi</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Interface</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>MAC</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>IP</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Hostname</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Expected</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Detected As</th>
                  <th style={{ padding: '0.75rem', textAlign: 'left' }}>Activity</th>
                  <th style={{ padding: '0.75rem', textAlign: 'center' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {correlations.map((corr, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.02)'
                    }}
                  >
                    <td style={{ padding: '0.75rem' }}>{corr.pi_id}</td>
                    <td style={{ padding: '0.75rem', fontFamily: 'monospace' }}>
                      {corr.interface}
                    </td>
                    <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                      {corr.mac_address}
                    </td>
                    <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                      {corr.ip_address || '-'}
                    </td>
                    <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                      {corr.r1_hostname || '-'}
                    </td>
                    <td style={{
                      padding: '0.75rem',
                      textTransform: 'capitalize',
                      fontWeight: '500'
                    }}>
                      {corr.expected_personality}
                    </td>
                    <td style={{ padding: '0.75rem' }}>
                      {corr.r1_detected_os || '-'}
                    </td>
                    <td style={{ padding: '0.75rem' }}>
                      {corr.traffic && corr.traffic.active ? (
                        <div>
                          <div style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.25rem 0.5rem',
                            background: 'rgba(0, 229, 255, 0.1)',
                            border: '1px solid rgba(0, 229, 255, 0.3)',
                            borderRadius: '4px',
                            fontSize: '0.875rem'
                          }}>
                            <span style={{
                              width: '6px',
                              height: '6px',
                              borderRadius: '50%',
                              background: 'var(--signal-green)',
                              display: 'inline-block'
                            }}></span>
                            {corr.traffic.type.replace('_', ' ')}
                          </div>
                          {corr.traffic.stats && Object.keys(corr.traffic.stats).length > 0 && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                              {Object.entries(corr.traffic.stats).slice(0, 2).map(([key, value]) => (
                                <span key={key} style={{ marginRight: '0.5rem' }}>
                                  {key}: {typeof value === 'number' ? value.toLocaleString() : value}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                          {corr.state === 'connected' ? 'idle' : corr.state || '-'}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem', textAlign: 'center' }}>
                      <span style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: '9999px',
                        fontSize: '0.875rem',
                        fontWeight: '500',
                        background: corr.detection_correct
                          ? 'rgba(0, 255, 136, 0.15)'
                          : corr.r1_detected_os
                            ? 'rgba(255, 34, 102, 0.15)'
                            : 'rgba(255, 255, 255, 0.05)',
                        border: corr.detection_correct
                          ? '1px solid rgba(0, 255, 136, 0.3)'
                          : corr.r1_detected_os
                            ? '1px solid rgba(255, 34, 102, 0.3)'
                            : '1px solid rgba(255, 255, 255, 0.1)',
                        color: corr.detection_correct
                          ? 'var(--signal-green)'
                          : corr.r1_detected_os
                            ? 'var(--signal-red)'
                            : 'var(--text-secondary)'
                      }}>
                        {getDetectionLabel(corr)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default RuckusOne;

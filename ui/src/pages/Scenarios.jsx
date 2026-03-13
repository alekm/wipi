import { useState, useEffect } from 'react';
import { scenarioApi, piApi, pskSetApi, residentSimApi } from '../api/client';

function emptyScenario() {
  return {
    id: '',
    name: '',
    description: '',
    pis: [],
  };
}

function Scenarios() {
  const [scenarios, setScenarios] = useState([]);
  const [pis, setPis] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [editingScenario, setEditingScenario] = useState(null);
  const [isNew, setIsNew] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const [pskImportLoading, setPskImportLoading] = useState(false);
  const [residentStatus, setResidentStatus] = useState(null);
  const [residentLoading, setResidentLoading] = useState(false);
  const [pskSets, setPskSets] = useState([]);

  useEffect(() => {
    loadData();
    loadResidentStatus();
  }, []);

  async function loadData() {
    try {
      const [scenariosData, pisData, pskSetsData] = await Promise.all([
        scenarioApi.list(),
        piApi.list(),
        pskSetApi.list(),
      ]);

      setScenarios(scenariosData);
      setPis(pisData);
      setPskSets(pskSetsData);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadResidentStatus() {
    try {
      setResidentLoading(true);
      const status = await residentSimApi.getStatus();
      setResidentStatus(status);
    } catch (err) {
      // Non-fatal; just log
      console.error('Failed to load resident simulation status:', err);
    } finally {
      setResidentLoading(false);
    }
  }

  function beginCreateScenario() {
    setIsNew(true);
    setEditingScenario(emptyScenario());
    setSelectedScenario(null);
    setActionMessage(null);
  }

  function beginEditScenario(scenario) {
    setIsNew(false);
    setEditingScenario({
      id: scenario.id,
      name: scenario.name || '',
      description: scenario.description || '',
      pis: scenario.pis || [],
    });
    setSelectedScenario(scenario);
    setActionMessage(null);
  }

  function cancelEdit() {
    setEditingScenario(null);
    setIsNew(false);
  }

  async function saveScenario(e) {
    e.preventDefault();
    if (!editingScenario) return;

    setActionLoading(true);
    setActionMessage(null);

    try {
      const payload = {
        id: editingScenario.id || undefined,
        name: editingScenario.name,
        description: editingScenario.description,
        pis: editingScenario.pis,
      };

      if (isNew) {
        await scenarioApi.create(payload);
        setActionMessage({ type: 'success', text: 'Scenario created successfully.' });
      } else {
        await scenarioApi.update(editingScenario.id, payload);
        setActionMessage({ type: 'success', text: 'Scenario updated successfully.' });
      }

      setEditingScenario(null);
      setIsNew(false);
      await loadData();
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to save scenario: ${err.message}`,
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function deleteScenario(scenarioId) {
    if (!window.confirm('Delete this scenario? This cannot be undone.')) {
      return;
    }

    setActionLoading(true);
    setActionMessage(null);

    try {
      await scenarioApi.delete(scenarioId);
      setActionMessage({ type: 'success', text: 'Scenario deleted.' });
      if (selectedScenario?.id === scenarioId) {
        setSelectedScenario(null);
      }
      if (editingScenario?.id === scenarioId) {
        setEditingScenario(null);
      }
      await loadData();
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to delete scenario: ${err.message}`,
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function applyScenario(scenarioId) {
    setActionLoading(true);
    setActionMessage(null);

    try {
      const result = await scenarioApi.apply(scenarioId);
      setActionMessage({
        type: 'success',
        text: `Scenario applied successfully! State: ${result.state}`,
      });

      // Refresh scenarios after a delay
      setTimeout(loadData, 2000);
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to apply scenario: ${err.message}`,
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function stopScenario(scenarioId) {
    setActionLoading(true);
    setActionMessage(null);

    try {
      await scenarioApi.stop(scenarioId);
      setActionMessage({
        type: 'success',
        text: 'Scenario stopped successfully!',
      });

      setTimeout(loadData, 2000);
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to stop scenario: ${err.message}`,
      });
    } finally {
      setActionLoading(false);
    }
  }

  async function validateScenario(scenarioId) {
    try {
      const result = await scenarioApi.validate(scenarioId);

      if (result.valid) {
        setActionMessage({
          type: 'success',
          text:
            'Scenario is valid! ' +
            (result.warnings?.length > 0 ? `(${result.warnings.length} warnings)` : ''),
        });
      } else {
        setActionMessage({
          type: 'error',
          text: `Validation failed: ${result.errors?.join(', ')}`,
        });
      }
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Validation error: ${err.message}`,
      });
    }
  }

  function selectScenario(scenario) {
    setSelectedScenario(selectedScenario?.id === scenario.id ? null : scenario);
    setActionMessage(null);
  }

  const onlinePis = pis.filter((pi) => pi.status === 'online');

  return (
    <div className="scenarios-main">
      {actionMessage && (
        <div
          className={
            actionMessage.type === 'success'
              ? 'alert alert-success'
              : 'alert alert-error'
          }
        >
          {actionMessage.text}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Resident Simulation</h2>
            <div style={{ fontSize: '0.9rem', color: '#7f8c8d' }}>
              {onlinePis.length} Pi(s) online
            </div>
          </div>
        </div>
        <ResidentSimulationPanel
          status={residentStatus}
          loading={residentLoading}
          onReload={loadResidentStatus}
          setActionMessage={setActionMessage}
          pskSets={pskSets}
        />
      </div>

      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Import PSK CSV</h2>
        </div>
        <PskImportForm
          loading={pskImportLoading}
          setLoading={setPskImportLoading}
          setActionMessage={setActionMessage}
        />
      </div>

      {pskSets && pskSets.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">PSK Sets</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>SSID</th>
                <th>PSK Count</th>
              </tr>
            </thead>
            <tbody>
              {pskSets.map((set) => (
                <tr key={set.id}>
                  <td style={{ fontWeight: '500' }}>{set.id}</td>
                  <td>{set.name}</td>
                  <td>{set.ssid}</td>
                  <td>{set.psk_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ResidentSimulationPanel({ status, loading, onReload, setActionMessage, pskSets }) {
  const [enabled, setEnabled] = useState(false);
  const [pskSetId, setPskSetId] = useState('');
  const [targetActive, setTargetActive] = useState(64);
  const [rotationHours, setRotationHours] = useState(6);
  const [maxInterfacesPerPi, setMaxInterfacesPerPi] = useState(8);
  const [submitting, setSubmitting] = useState(false);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    if (status) {
      setEnabled(status.enabled);
      setPskSetId(status.psk_set_id || '');
      setTargetActive(status.target_active_apartments);
      setRotationHours(status.rotation_hours);
      setMaxInterfacesPerPi(status.max_interfaces_per_pi);
    }
  }, [status]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setActionMessage(null);

    try {
      const payload = {
        enabled,
        psk_set_id: pskSetId,
        target_active_apartments: Number(targetActive),
        rotation_hours: Number(rotationHours),
        max_interfaces_per_pi: Number(maxInterfacesPerPi),
      };
      const updated = await residentSimApi.updateConfig(payload);
      setActionMessage({
        type: 'success',
        text: `Resident simulation ${updated.enabled ? 'enabled' : 'disabled'} (active apartments: ${updated.active_apartments}).`,
      });
      await onReload();
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to update resident simulation: ${err.message}`,
      });
    } finally {
      setSubmitting(false);
    }
  }

  const lastRotation =
    status && status.last_rotation_at ? new Date(status.last_rotation_at).toLocaleString() : 'N/A';
  const nextRotation =
    status && status.next_rotation_at ? new Date(status.next_rotation_at).toLocaleString() : 'N/A';

  return (
    <form className="scenario-form" onSubmit={handleSubmit}>
      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />{' '}
          Enable resident simulation
        </label>
        <div className="form-help">
          When enabled, Pis will be continuously configured to simulate active apartments.
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="resident-psk-set">PSK Set</label>
        <select
          id="resident-psk-set"
          value={pskSetId}
          onChange={(e) => setPskSetId(e.target.value)}
          required
        >
          <option value="">Select a PSK set…</option>
          {pskSets &&
            pskSets.map((set) => (
              <option key={set.id} value={set.id}>
                {set.id} ({set.ssid}) – {set.psk_count ?? 0} PSKs
              </option>
            ))}
        </select>
        <div className="form-help">
          Choose which imported DPSK set to use for apartments.
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="resident-target">Target active apartments</label>
        <input
          id="resident-target"
          type="number"
          min={1}
          value={targetActive}
          onChange={(e) => setTargetActive(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="resident-rotation">Rotation interval (hours)</label>
        <input
          id="resident-rotation"
          type="number"
          min={0.25}
          step={0.25}
          value={rotationHours}
          onChange={(e) => setRotationHours(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="resident-max-ifaces">Max interfaces per Pi</label>
        <input
          id="resident-max-ifaces"
          type="number"
          min={1}
          value={maxInterfacesPerPi}
          onChange={(e) => setMaxInterfacesPerPi(e.target.value)}
        />
      </div>

      {status && (
        <div className="form-help">
          <div>Active apartments: {status.active_apartments}</div>
          <div>Total apartments in PSK set: {status.total_apartments}</div>
          <div>Last rotation: {lastRotation}</div>
          <div>Next rotation: {nextRotation}</div>
        </div>
      )}

      <div className="scenario-form-actions">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={submitting || stopping || loading}
        >
          {submitting ? 'Updating...' : 'Update Simulation'}
        </button>
        {status && status.enabled && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={submitting || stopping || loading}
            onClick={async () => {
              setStopping(true);
              setActionMessage(null);
              try {
                await residentSimApi.stop();
                setActionMessage({ type: 'success', text: 'Simulation stopped and all Pi configurations cleared.' });
                await onReload();
              } catch (err) {
                setActionMessage({ type: 'error', text: `Failed to stop simulation: ${err.message}` });
              } finally {
                setStopping(false);
              }
            }}
          >
            {stopping ? 'Stopping...' : 'Stop Simulation'}
          </button>
        )}
      </div>
    </form>
  );
}

function PskImportForm({ loading, setLoading, setActionMessage }) {
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [ssid, setSsid] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) {
      setActionMessage({
        type: 'error',
        text: 'Please select a CSV file to import.',
      });
      return;
    }

    setLoading(true);
    setActionMessage(null);

    try {
      const effectiveName = name || id;
      await pskSetApi.importCsv({
        id,
        name: effectiveName,
        ssid,
        description,
        file,
      });
      setActionMessage({
        type: 'success',
        text: `PSK set "${effectiveName}" imported successfully.`,
      });
      setFile(null);
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: `Failed to import PSK CSV: ${err.message}`,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="scenario-form" onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="psk-id">PSK Set ID</label>
        <input
          id="psk-id"
          type="text"
          value={id}
          onChange={(e) => setId(e.target.value)}
          required
          placeholder="e.g. mdu360-dpsk"
        />
      </div>

      <div className="form-group">
        <label htmlFor="psk-name">Name</label>
        <input
          id="psk-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Friendly label (default: same as ID)"
        />
      </div>

      <div className="form-group">
        <label htmlFor="psk-ssid">SSID</label>
        <input
          id="psk-ssid"
          type="text"
          value={ssid}
          onChange={(e) => setSsid(e.target.value)}
          required
          placeholder="SSID these PSKs are valid for"
        />
      </div>

      <div className="form-group">
        <label htmlFor="psk-description">Description</label>
        <textarea
          id="psk-description"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional notes (e.g. source CSV, date)"
        />
      </div>

      <div className="form-group">
        <label htmlFor="psk-file">DPSK CSV File</label>
        <input
          id="psk-file"
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <div className="form-help">
          Expects the DPSK export format with a <code>Passphrase</code> column.
        </div>
      </div>

      <div className="scenario-form-actions">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? 'Importing...' : 'Import PSK CSV'}
        </button>
      </div>
    </form>
  );
}

export default Scenarios;

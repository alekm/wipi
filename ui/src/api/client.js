// API client for WiPi Controller

const API_BASE = '/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include', // Include cookies for authentication
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || error.detail || 'Request failed');
  }

  return response.json();
}

// Pi Management
export const piApi = {
  list: () => request('/pis'),
  get: (piId) => request(`/pis/${piId}`),
  getStatus: (piId) => request(`/pis/${piId}/status`),
  register: (data) => request('/pis/register', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  delete: (piId) => request(`/pis/${piId}`, { method: 'DELETE' }),
};

// Scenario Management
export const scenarioApi = {
  list: () => request('/scenarios'),
  get: (scenarioId) => request(`/scenarios/${scenarioId}`),
  create: (data) => request('/scenarios', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (scenarioId, data) => request(`/scenarios/${scenarioId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (scenarioId) => request(`/scenarios/${scenarioId}`, { method: 'DELETE' }),
  validate: (scenarioId) => request(`/scenarios/${scenarioId}/validate`, {
    method: 'POST',
  }),
  apply: (scenarioId) => request(`/scenarios/${scenarioId}/apply`, {
    method: 'POST',
  }),
  stop: (scenarioId) => request(`/scenarios/${scenarioId}/stop`, {
    method: 'POST',
  }),
  getStatus: (scenarioId) => request(`/scenarios/${scenarioId}/status`),
};

// Monitoring
export const monitoringApi = {
  getOverallStatus: () => request('/status'),
};

// PSK Sets
export const pskSetApi = {
  list: () => request('/psk_sets'),
  importCsv: async ({ id, name, ssid, description, file }) => {
    const formData = new FormData();
    formData.append('id', id);
    formData.append('name', name);
    formData.append('ssid', ssid);
    if (description) {
      formData.append('description', description);
    }
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/psk_sets/import_csv`, {
      method: 'POST',
      credentials: 'include', // Include cookies for authentication
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || error.detail || 'Import failed');
    }

    return response.json();
  },
};

// Resident Simulation
export const residentSimApi = {
  getStatus: () => request('/resident_simulation/status'),
  updateConfig: (data) =>
    request('/resident_simulation/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Ruckus One Integration
export const ruckusOneApi = {
  getStatus: () => request('/ruckus_one/status'),
  getClients: () => request('/ruckus_one/clients'),
  getConfig: () => request('/ruckus_one/config'),
  configure: (data) =>
    request('/ruckus_one/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export default {
  pi: piApi,
  scenario: scenarioApi,
  monitoring: monitoringApi,
  pskSet: pskSetApi,
  residentSim: residentSimApi,
  ruckusOne: ruckusOneApi,
};

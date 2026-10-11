/**
 * CrisisGrid API Client
 */

let API_BASE_URL = 'http://localhost:8000';

export function setApiBaseUrl(url) {
  API_BASE_URL = url.replace(/\/+$/, '');
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      let errText = await res.text();
      try {
        const parsed = JSON.parse(errText);
        errText = parsed.detail || errText;
      } catch (e) {}
      throw new Error(`[${res.status}] ${errText}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  // Health
  checkHealth: () => request('/health'),

  // Experiments
  listExperiments: () => request('/experiments'),
  getExperiment: (id) => request(`/experiments/${id}`),
  getExperimentSpec: (id) => request(`/experiments/${id}/spec`),
  getEvidence: (id) => request(`/experiments/${id}/evidence`),
  getDiscrepancies: (id) => request(`/experiments/${id}/discrepancies`),
  
  // Ingestion
  ingest: async (formData) => {
    const url = `${API_BASE_URL}/experiments/ingest`;
    const res = await fetch(url, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`[${res.status}] ${errText}`);
    }
    return await res.json();
  },

  // Graph
  getGraph: (id) => request(`/experiments/${id}/graph`),
  generateGraph: (id, force = false) => request(`/experiments/${id}/graph/generate?force=${force}`, { method: 'POST' }),
  tuneGraph: (id, payload) => request(`/experiments/${id}/graph/tune`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  getGraphVersions: (id) => request(`/experiments/${id}/graph/versions`),
  getGraphVersion: (id, verId) => request(`/experiments/${id}/graph/versions/${verId}`),
  getGraphDiff: (id, fromVer, toVer) => {
    let q = '';
    if (fromVer || toVer) {
      const params = new URLSearchParams();
      if (fromVer) params.append('from_version', fromVer);
      if (toVer) params.append('to_version', toVer);
      q = `?${params.toString()}`;
    }
    return request(`/experiments/${id}/graph/diff${q}`);
  },
  validateGraph: (id, verId = null) => request(`/experiments/${id}/graph/validate${verId ? `?version_id=${verId}` : ''}`),
  remediateGraph: (id, verId = null) => request(`/experiments/${id}/graph/remediate${verId ? `?version_id=${verId}` : ''}`, { method: 'POST' }),

  // Feasibility
  getFeasibility: (id, verId) => request(`/experiments/${id}/feasibility${verId ? `?version_id=${verId}` : ''}`),

  // Environment & Pre-Flight Imports
  getEnvironmentPreview: (id, verId = null, dockerImage = null, extraPackages = []) => {
    const params = new URLSearchParams();
    if (verId) params.append('version_id', verId);
    if (dockerImage) params.append('docker_image', dockerImage);
    if (extraPackages && extraPackages.length > 0) {
      extraPackages.forEach((p) => params.append('extra_packages', p));
    }
    const q = params.toString() ? `?${params.toString()}` : '';
    return request(`/experiments/${id}/environment-preview${q}`);
  },
  prepareEnvironment: (id, payload) => request(`/experiments/${id}/prepare-environment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  getEnvironmentBuildProgress: (id) => request(`/experiments/${id}/environment-build-progress`),

  // Execution Runner
  submitExecution: (id, payload) => request(`/experiments/${id}/executions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  listExecutions: (id) => request(`/experiments/${id}/executions`),
  getLatestExecution: (id) => request(`/experiments/${id}/executions/latest`),
  getExecution: (id, execId) => request(`/experiments/${id}/executions/${execId}`),
  cancelExecution: (id, execId) => request(`/experiments/${id}/executions/${execId}/cancel`, { method: 'POST' }),
  getProgress: (id, execId) => request(`/experiments/${id}/executions/${execId}/progress`),
  getSeeds: (id, execId, seed = null) => request(`/experiments/${id}/executions/${execId}/seeds${seed !== null ? `?seed=${seed}` : ''}`),
  resumeExecution: (id, execId, payload) => request(`/experiments/${id}/executions/${execId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),
  getRunEvidence: (id, execId) => request(`/experiments/${id}/executions/${execId}/evidence`),

  // Audit
  runStaticAudit: (id, includeLlm = true) => request(`/experiments/${id}/audit/static?include_llm=${includeLlm}`, { method: 'POST' }),
  runRunAudit: (id, execId = null) => request(`/experiments/${id}/audit/run${execId ? `?execution_id=${execId}` : ''}`, { method: 'POST' }),
  getAudit: (id) => request(`/experiments/${id}/audit`),

  // Report
  generateReport: (id) => request(`/experiments/${id}/report`, { method: 'POST' }),
  getReport: (id) => request(`/experiments/${id}/report`),
  getReportMarkdownUrl: (id) => `${API_BASE_URL}/experiments/${id}/report.md`,
};

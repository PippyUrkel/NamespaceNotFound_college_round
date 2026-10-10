import React, { useState, useEffect } from 'react';
import { 
  Layers, GitFork, Cpu, Play, ShieldCheck, RefreshCw, Plus, 
  Sparkles, Wifi, WifiOff, FileText, CheckCircle2, AlertCircle 
} from 'lucide-react';
import { api, setApiBaseUrl, getApiBaseUrl } from './api';
import IngestionTab from './components/IngestionTab';
import GraphTab from './components/GraphTab';
import FeasibilityTab from './components/FeasibilityTab';
import RunnerTab from './components/RunnerTab';
import EvidenceTab from './components/EvidenceTab';
import IngestModal from './components/IngestModal';

export default function App() {
  const [backendUrl, setBackendUrl] = useState(getApiBaseUrl());
  const [backendOnline, setBackendOnline] = useState(false);
  const [experiments, setExperiments] = useState([]);
  const [selectedExpId, setSelectedExpId] = useState('');
  const [activeTab, setActiveTab] = useState('graph');

  // Experiment data
  const [spec, setSpec] = useState(null);
  const [graph, setGraph] = useState(null);
  const [versions, setVersions] = useState([]);
  const [feasibility, setFeasibility] = useState(null);
  const [latestExecution, setLatestExecution] = useState(null);
  const [discrepancies, setDiscrepancies] = useState([]);

  // Modals & loading
  const [showIngestModal, setShowIngestModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  // Check backend health & list experiments on mount
  useEffect(() => {
    checkHealthAndLoad();
  }, [backendUrl]);

  async function checkHealthAndLoad() {
    setApiBaseUrl(backendUrl);
    try {
      await api.checkHealth();
      setBackendOnline(true);
      await loadExperiments();
    } catch (e) {
      setBackendOnline(false);
    }
  }

  async function loadExperiments() {
    try {
      const list = await api.listExperiments();
      setExperiments(list || []);
      if (list && list.length > 0 && !selectedExpId) {
        setSelectedExpId(list[0].experiment_id);
      }
    } catch (e) {
      console.warn('Failed to list experiments:', e);
    }
  }

  // Load selected experiment details
  useEffect(() => {
    if (selectedExpId) {
      loadExperimentDetails(selectedExpId);
    }
  }, [selectedExpId]);

  async function loadExperimentDetails(expId) {
    setLoading(true);
    try {
      // 1. Load Spec
      try {
        const specData = await api.getExperimentSpec(expId);
        setSpec(specData);
      } catch (e) {
        setSpec(null);
      }

      // 2. Load Graph & Versions
      try {
        const graphData = await api.getGraph(expId);
        setGraph(graphData);
      } catch (e) {
        setGraph(null);
      }

      try {
        const vers = await api.getGraphVersions(expId);
        setVersions(vers || []);
      } catch (e) {
        setVersions([]);
      }

      // 3. Load Feasibility
      try {
        const feas = await api.getFeasibility(expId);
        setFeasibility(feas);
      } catch (e) {
        setFeasibility(null);
      }

      // 4. Load Latest Execution
      try {
        const exec = await api.getLatestExecution(expId);
        setLatestExecution(exec);
      } catch (e) {
        setLatestExecution(null);
      }

      // 5. Load Discrepancies
      try {
        const disc = await api.getDiscrepancies(expId);
        setDiscrepancies(disc.discrepancies || []);
      } catch (e) {
        setDiscrepancies([]);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleVersionChange(verId) {
    if (!selectedExpId) return;
    try {
      const verGraph = await api.getGraphVersion(selectedExpId, verId);
      setGraph(verGraph);
    } catch (e) {
      alert('Failed to load version: ' + e.message);
    }
  }

  async function handleQuickDemo() {
    setDemoLoading(true);
    try {
      const formData = new FormData();
      formData.append('repo_url', 'https://github.com/facebookresearch/reproducibility-benchmark');
      formData.append('branch', 'main');
      const res = await api.ingest(formData);
      await loadExperiments();
      setSelectedExpId(res.experiment_id);
      setActiveTab('graph');
    } catch (err) {
      alert('Demo creation failed: ' + err.message);
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* App Header */}
      <header className="app-header">
        <div className="container header-content">
          <div className="logo-group">
            <div className="logo-icon">
              <Layers size={20} />
            </div>
            <div>
              <div className="app-title">CrisisGrid Studio</div>
              <div className="app-subtitle">Reproducibility Pipeline Inspector</div>
            </div>
          </div>

          <div className="header-actions">
            {/* Backend Connection */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <input
                type="text"
                className="input"
                style={{ width: '190px', fontSize: '0.78rem', padding: '0.35rem 0.6rem' }}
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                placeholder="http://localhost:8000"
              />
              <span className={`badge ${backendOnline ? 'badge-green' : 'badge-red'}`}>
                {backendOnline ? <Wifi size={12} /> : <WifiOff size={12} />}
                {backendOnline ? 'Online' : 'Offline'}
              </span>
            </div>

            {/* Ingest New */}
            <button className="btn btn-secondary btn-sm" onClick={() => setShowIngestModal(true)}>
              <Plus size={14} /> Ingest Research Paper
            </button>

            {/* Quick Demo */}
            <button className="btn btn-primary btn-sm" onClick={handleQuickDemo} disabled={demoLoading}>
              <Sparkles size={14} /> {demoLoading ? 'Generating Demo...' : 'Quick Demo'}
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="container" style={{ flex: 1, paddingBottom: '3rem', paddingTop: '1.25rem' }}>
        {/* Experiment Selector & Banner */}
        <div className="card" style={{ marginBottom: '1.25rem', padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                Active Experiment:
              </span>
              <select
                className="select"
                style={{ minWidth: '280px', fontWeight: 600 }}
                value={selectedExpId}
                onChange={(e) => setSelectedExpId(e.target.value)}
              >
                {experiments.length > 0 ? (
                  experiments.map((exp) => (
                    <option key={exp.experiment_id} value={exp.experiment_id}>
                      {exp.title ? `${exp.title.slice(0, 35)}...` : exp.experiment_id} ({exp.experiment_id.slice(0, 8)})
                    </option>
                  ))
                ) : (
                  <option value="">No experiments found</option>
                )}
              </select>

              <button className="btn btn-secondary btn-sm" onClick={() => loadExperiments()}>
                <RefreshCw size={13} />
              </button>
            </div>

            {spec && (
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <span>Dataset: <strong style={{ color: 'var(--accent-cyan)' }}>{spec.dataset || 'CIFAR-10'}</strong></span>
                <span>•</span>
                <span>Active Graph: <strong style={{ color: 'var(--accent-indigo)' }}>{graph?.version_id || 'v1'}</strong></span>
                <span>•</span>
                <span>Runs: <strong style={{ color: 'var(--accent-green)' }}>{latestExecution ? '1 recorded' : '0'}</strong></span>
              </div>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="tab-bar" style={{ marginBottom: '1.25rem' }}>
          <button 
            className={`tab-btn ${activeTab === 'ingest' ? 'active' : ''}`}
            onClick={() => setActiveTab('ingest')}
          >
            <FileText size={16} /> Overview & Ingestion
          </button>

          <button 
            className={`tab-btn ${activeTab === 'graph' ? 'active' : ''}`}
            onClick={() => setActiveTab('graph')}
          >
            <GitFork size={16} /> Experiment Graph (DAG)
          </button>

          <button 
            className={`tab-btn ${activeTab === 'feasibility' ? 'active' : ''}`}
            onClick={() => setActiveTab('feasibility')}
          >
            <Cpu size={16} /> Feasibility Assessment
          </button>

          <button 
            className={`tab-btn ${activeTab === 'runner' ? 'active' : ''}`}
            onClick={() => setActiveTab('runner')}
          >
            <Play size={16} /> Execution Runner
          </button>

          <button 
            className={`tab-btn ${activeTab === 'evidence' ? 'active' : ''}`}
            onClick={() => setActiveTab('evidence')}
          >
            <ShieldCheck size={16} /> Provenance & Audit Evidence
          </button>
        </div>

        {/* Tab Content */}
        {selectedExpId ? (
          <div>
            {activeTab === 'ingest' && (
              <IngestionTab 
                spec={spec} 
                conditionProvenance={graph?.condition_provenance}
                discrepancies={discrepancies}
              />
            )}

            {activeTab === 'graph' && (
              <GraphTab
                experimentId={selectedExpId}
                graph={graph}
                versions={versions}
                onVersionChange={handleVersionChange}
                onRefreshGraph={() => loadExperimentDetails(selectedExpId)}
              />
            )}

            {activeTab === 'feasibility' && (
              <FeasibilityTab feasibility={feasibility} />
            )}

            {activeTab === 'runner' && (
              <RunnerTab
                experimentId={selectedExpId}
                activeVersionId={graph?.version_id}
                latestExecution={latestExecution}
                onRefreshExecution={() => loadExperimentDetails(selectedExpId)}
              />
            )}

            {activeTab === 'evidence' && (
              <EvidenceTab
                experimentId={selectedExpId}
                latestExecution={latestExecution}
              />
            )}
          </div>
        ) : (
          <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Welcome to CrisisGrid Studio
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1.5rem', maxWidth: '480px', margin: '0 auto 1.5rem' }}>
              No research experiment is currently selected. Click <strong>Quick Demo</strong> to instantly generate a full reproducible experiment pipeline, or ingest your own paper PDF.
            </p>
            <button className="btn btn-primary" onClick={handleQuickDemo} disabled={demoLoading}>
              <Sparkles size={16} /> {demoLoading ? 'Generating Demo...' : 'Generate Quick Demo Experiment'}
            </button>
          </div>
        )}
      </main>

      {/* Ingestion Modal */}
      <IngestModal
        isOpen={showIngestModal}
        onClose={() => setShowIngestModal(false)}
        onIngested={async (newId) => {
          await loadExperiments();
          setSelectedExpId(newId);
          setActiveTab('graph');
        }}
      />
    </div>
  );
}

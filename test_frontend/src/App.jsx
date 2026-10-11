import React, { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  LayoutDashboard,
  FileText,
  GitFork,
  Cpu,
  Play,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Plus,
  Sparkles,
  Wifi,
  WifiOff,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  ArrowUpRight,
  UploadCloud,
  Search,
  Database,
  AlertTriangle,
  X,
} from 'lucide-react';

import { api, setApiBaseUrl, getApiBaseUrl } from './api';
import IngestionTab from './components/IngestionTab';
import GraphTab from './components/GraphTab';
import FeasibilityTab from './components/FeasibilityTab';
import RunnerTab from './components/RunnerTab';
import EvidenceTab from './components/EvidenceTab';
import AuditTab from './components/AuditTab';
import IngestModal from './components/IngestModal';
import './App.css';

const NAV_GROUPS = [
  {
    label: 'WORKSPACE',
    items: [
      { id: 'ingest', label: 'Overview & Ingestion', shortLabel: 'Overview', Icon: LayoutDashboard },
    ],
  },
  {
    label: 'EXPERIMENT',
    items: [
      { id: 'graph', label: 'Experiment Graph', Icon: GitFork },
      { id: 'feasibility', label: 'Feasibility Assessment', Icon: Cpu },
      { id: 'runner', label: 'Execution Runner', Icon: Play },
    ],
  },
  {
    label: 'VERIFICATION',
    items: [
      { id: 'evidence', label: 'Provenance & Evidence', Icon: ShieldCheck },
      { id: 'audit', label: 'Audit & Report', Icon: CheckCircle2 },
    ],
  },
];

const TAB_LABELS = {
  ingest: 'Overview & Ingestion',
  graph: 'Experiment Graph',
  feasibility: 'Feasibility Assessment',
  runner: 'Execution Runner',
  evidence: 'Provenance & Evidence',
  audit: 'Audit & Report',
};

function getExperimentLabel(experiment) {
  if (!experiment) return 'Untitled experiment';
  const title = experiment.title || experiment.name;
  if (title) return title;
  return `Experiment ${String(experiment.experiment_id || '').slice(0, 8)}`;
}

export default function App() {
  const [backendUrl, setBackendUrl] = useState(getApiBaseUrl());
  const [backendOnline, setBackendOnline] = useState(false);
  const [experiments, setExperiments] = useState([]);
  const [selectedExpId, setSelectedExpId] = useState('');
  const [activeTab, setActiveTab] = useState('ingest');

  const [spec, setSpec] = useState(null);
  const [graph, setGraph] = useState(null);
  const [versions, setVersions] = useState([]);
  const [feasibility, setFeasibility] = useState(null);
  const [latestExecution, setLatestExecution] = useState(null);
  const [discrepancies, setDiscrepancies] = useState([]);

  const [showIngestModal, setShowIngestModal] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [experimentsLoading, setExperimentsLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notice, setNotice] = useState('');

  const hasExperiment = Boolean(selectedExpId);
  const selectedExperiment = experiments.find(
    (experiment) => experiment.experiment_id === selectedExpId
  );

  const checkHealthAndLoad = useCallback(async () => {
    setApiBaseUrl(backendUrl);
    try {
      await api.checkHealth();
      setBackendOnline(true);
      await loadExperiments();
    } catch {
      setBackendOnline(false);
    }
  }, [backendUrl]);

  const loadExperiments = useCallback(async () => {
    setExperimentsLoading(true);
    try {
      const list = await api.listExperiments();
      const safeList = list || [];
      setExperiments(safeList);
      // Do not auto-select an experiment: an empty workspace should remain a
      // genuine landing page until the user chooses or creates an experiment.
      setSelectedExpId((currentId) => (
        currentId && safeList.some((item) => item.experiment_id === currentId)
          ? currentId
          : ''
      ));
    } catch (error) {
      console.warn('Failed to list experiments:', error);
      setNotice(`Could not load experiments: ${error.message}`);
    } finally {
      setExperimentsLoading(false);
    }
  }, []);

  const loadExperimentDetails = useCallback(async (expId) => {
    if (!expId) return;
    setDetailsLoading(true);

    const safeLoad = async (request, fallback) => {
      try {
        return await request();
      } catch {
        return fallback;
      }
    };

    try {
      const [
        nextSpec,
        nextGraph,
        nextVersions,
        nextFeasibility,
        nextExecution,
        nextDiscrepancies,
      ] = await Promise.all([
        safeLoad(() => api.getExperimentSpec(expId), null),
        safeLoad(() => api.getGraph(expId), null),
        safeLoad(() => api.getGraphVersions(expId), []),
        safeLoad(() => api.getFeasibility(expId), null),
        safeLoad(() => api.getLatestExecution(expId), null),
        safeLoad(() => api.getDiscrepancies(expId), { discrepancies: [] }),
      ]);

      setSpec(nextSpec);
      setGraph(nextGraph);
      setVersions(nextVersions || []);
      setFeasibility(nextFeasibility);
      setLatestExecution(nextExecution);
      setDiscrepancies(nextDiscrepancies?.discrepancies || []);
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkHealthAndLoad();
  }, [checkHealthAndLoad]);

  useEffect(() => {
    if (selectedExpId) {
      loadExperimentDetails(selectedExpId);
    } else {
      setSpec(null);
      setGraph(null);
      setVersions([]);
      setFeasibility(null);
      setLatestExecution(null);
      setDiscrepancies([]);
    }
  }, [selectedExpId, loadExperimentDetails]);

  async function handleVersionChange(versionId) {
    if (!selectedExpId) return;
    try {
      const versionGraph = await api.getGraphVersion(selectedExpId, versionId);
      setGraph(versionGraph);
    } catch (error) {
      window.alert(`Failed to load version: ${error.message}`);
    }
  }

  async function handleQuickDemo() {
    setDemoLoading(true);
    setNotice('');
    try {
      const formData = new FormData();
      formData.append(
        'repo_url',
        'https://github.com/facebookresearch/reproducibility-benchmark'
      );
      formData.append('branch', 'main');

      const result = await api.ingest(formData);
      await loadExperiments();
      setSelectedExpId(result.experiment_id);
      setActiveTab('graph');
      setNotice('');
    } catch (error) {
      setNotice(`Demo creation failed: ${error.message}`);
    } finally {
      setDemoLoading(false);
    }
  }

  function handleNavigate(tabId) {
    setActiveTab(tabId);
    setMobileNavOpen(false);
    setNotice('');
  }

  function handleStartIngestion() {
    setShowIngestModal(true);
    setNotice('');
  }

  const activeTabLabel = TAB_LABELS[activeTab] || 'Workspace';

  return (
    <div className={`crisis-app ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      <header className="app-header">
        <a
          className="logo-group"
          href="#top"
          onClick={(event) => {
            event.preventDefault();
            if (hasExperiment) handleNavigate('ingest');
          }}
          aria-label="CrisisGrid home"
        >
          <span className="logo-icon"><Layers size={20} strokeWidth={1.8} /></span>
          <span className="logo-copy">
            <span className="app-title">CrisisGrid<span className="title-dot">.</span></span>
            <span className="app-subtitle">ML RESEARCH WORKSPACE <span className="header-index">/ 001</span></span>
          </span>
        </a>

        <div className="header-right">
          <div className="backend-control">
            {/* <span className="eyebrow">API ENDPOINT</span>
            <input
              type="text"
              className="input backend-input"
              value={backendUrl}
              onChange={(event) => setBackendUrl(event.target.value)}
              onBlur={checkHealthAndLoad}
              onKeyDown={(event) => {
                if (event.key === 'Enter') checkHealthAndLoad();
              }}
              placeholder="http://localhost:8000"
              aria-label="Backend API URL"
            /> */}
            <span className={`badge connection-badge ${backendOnline ? 'badge-green' : 'badge-red'}`}>
              {backendOnline ? <Wifi size={12} /> : <WifiOff size={12} />}
              {backendOnline ? 'Online' : 'Offline'}
            </span>
          </div>
          <button className="btn btn-secondary header-ingest" onClick={handleStartIngestion}>
            <Plus size={15} /> <span>Ingest paper</span>
          </button>
          {/* <button className="btn btn-primary" onClick={handleQuickDemo} disabled={demoLoading}>
            <Sparkles size={15} />
            <span>{demoLoading ? 'Preparing demo…' : 'Quick demo'}</span>
          </button> */}
          <button
            className="mobile-menu-button"
            onClick={() => setMobileNavOpen((open) => !open)}
            aria-label={mobileNavOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={mobileNavOpen}
          >
            {mobileNavOpen ? <X size={18} /> : <PanelLeftOpen size={18} />}
          </button>
        </div>
      </header>

      <div className="app-frame" id="top">
        {hasExperiment && (
          <>
            <aside className={`app-sidebar ${sidebarOpen ? '' : 'is-collapsed'} ${mobileNavOpen ? 'mobile-open' : ''}`}>
              <div className="sidebar-topline">
                <span className="eyebrow">RESEARCH NAVIGATION</span>
                <button
                  className="sidebar-toggle"
                  onClick={() => setSidebarOpen((open) => !open)}
                  aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
                  title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
                >
                  {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
                </button>
              </div>

              <div className="sidebar-experiment">
                <span className="sidebar-experiment-icon"><Database size={15} /></span>
                <div className="sidebar-experiment-copy">
                  <span className="eyebrow">ACTIVE EXPERIMENT</span>
                  <strong title={getExperimentLabel(selectedExperiment)}>{getExperimentLabel(selectedExperiment)}</strong>
                  <span className="sidebar-experiment-id">{selectedExpId.slice(0, 12)}</span>
                </div>
              </div>

              <nav className="sidebar-nav" aria-label="Experiment sections">
                {NAV_GROUPS.map((group) => (
                  <div className="nav-group" key={group.label}>
                    {sidebarOpen && <div className="nav-group-label">{group.label}</div>}
                    {group.items.map(({ id, label, shortLabel, Icon }) => (
                      <button
                        key={id}
                        className={`nav-item ${activeTab === id ? 'active' : ''}`}
                        onClick={() => handleNavigate(id)}
                        aria-current={activeTab === id ? 'page' : undefined}
                        title={sidebarOpen ? undefined : label}
                      >
                        <Icon size={17} strokeWidth={1.8} />
                        {sidebarOpen && <span>{shortLabel || label}</span>}
                        {sidebarOpen && activeTab === id && <span className="nav-active-mark" />}
                      </button>
                    ))}
                  </div>
                ))}
              </nav>

              <div className="sidebar-bottom">
                <div className={`sidebar-api-status ${backendOnline ? 'is-online' : 'is-offline'}`}>
                  <span className="status-dot" />
                  {sidebarOpen && <span>{backendOnline ? 'Backend connected' : 'Backend unavailable'}</span>}
                </div>
                <button className="sidebar-home-link" onClick={() => handleNavigate('ingest')}>
                  <LayoutDashboard size={16} />
                  {sidebarOpen && <span>Experiment overview</span>}
                </button>
              </div>
            </aside>
            {mobileNavOpen && <button className="mobile-nav-scrim" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation" />}
          </>
        )}

        <main className={`app-main ${hasExperiment ? 'has-sidebar' : 'landing-main'}`}>
          {hasExperiment ? (
            <>
              <section className="workspace-topbar">
                <div className="workspace-breadcrumb">
                  <span className="eyebrow">EXPERIMENT WORKSPACE</span>
                  <span className="breadcrumb-divider">/</span>
                  <span>{activeTabLabel}</span>
                </div>
                <div className="workspace-actions">
                  <label className="experiment-switcher">
                    <span className="eyebrow">ACTIVE</span>
                    <select
                      id="experiment-select"
                      className="select experiment-select"
                      value={selectedExpId}
                      onChange={(event) => {
                        setSelectedExpId(event.target.value);
                        setActiveTab('ingest');
                      }}
                      aria-label="Select active experiment"
                    >
                      {experiments.map((experiment) => (
                        <option key={experiment.experiment_id} value={experiment.experiment_id}>
                          {getExperimentLabel(experiment)} ({String(experiment.experiment_id).slice(0, 8)})
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={14} />
                  </label>
                  <button
                    className="icon-button"
                    onClick={loadExperiments}
                    disabled={experimentsLoading}
                    aria-label="Refresh experiments"
                    title="Refresh experiments"
                  >
                    <RefreshCw size={15} className={experimentsLoading ? 'is-spinning' : ''} />
                  </button>
                </div>
              </section>

              <section className="experiment-summary">
                <div className="summary-heading">
                  <div className="eyebrow section-kicker"><span className="live-indicator" /> ACTIVE RESEARCH RECORD</div>
                  <h1>{getExperimentLabel(selectedExperiment)}<span className="title-dot">.</span></h1>
                  <p>Inspect the pipeline. Trace the evidence. Reproduce the result.</p>
                </div>
                <div className="summary-metadata">
                  <div className="metadata-item">
                    <span>DATASET</span>
                    <strong className="text-research">{spec?.dataset || 'Not identified'}</strong>
                  </div>
                  <div className="metadata-divider" />
                  <div className="metadata-item">
                    <span>GRAPH VERSION</span>
                    <strong className="text-code">{graph?.version_id || '—'}</strong>
                  </div>
                  <div className="metadata-divider" />
                  <div className="metadata-item">
                    <span>RECORDED RUNS</span>
                    <strong className="text-success">{latestExecution ? '01' : '00'}</strong>
                  </div>
                </div>
              </section>

              {notice && (
                <div className="app-notice" role="status">
                  <AlertTriangle size={16} />
                  <span>{notice}</span>
                  <button onClick={() => setNotice('')} aria-label="Dismiss notice"><X size={15} /></button>
                </div>
              )}

              <section className="tab-content" aria-label={activeTabLabel}>
                {detailsLoading && !spec && !graph ? (
                  <div className="loading-state">
                    <span className="loading-mark" />
                    <span>Loading experiment workspace…</span>
                  </div>
                ) : (
                  <>
                    {activeTab === 'ingest' && (
                      <div className="tab-section-heading">
                        <div>
                          <span className="eyebrow">SOURCE INTAKE / 01</span>
                          <h2>Research ingestion</h2>
                          <p>Review the source material, repository snapshot, and evidence behind each scientific condition.</p>
                        </div>
                        <span className="audit-only-badge"><span className="status-dot" /> AUDIT VIEW</span>
                      </div>
                    )}
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
                    {activeTab === 'feasibility' && <FeasibilityTab feasibility={feasibility} />}
                    {activeTab === 'runner' && (
                      <RunnerTab
                        experimentId={selectedExpId}
                        activeVersionId={graph?.version_id}
                        latestExecution={latestExecution}
                        onRefreshExecution={() => loadExperimentDetails(selectedExpId)}
                        spec={spec}
                        graph={graph}
                      />
                    )}
                    {activeTab === 'evidence' && (
                      <EvidenceTab experimentId={selectedExpId} latestExecution={latestExecution} />
                    )}
                    {activeTab === 'audit' && (
                      <AuditTab experimentId={selectedExpId} latestExecution={latestExecution} />
                    )}
                  </>
                )}
              </section>
            </>
          ) : (
            <section className="ingestion-landing">
              <div className="landing-kicker"><span className="live-indicator" /> REPRODUCIBILITY WORKSPACE / 001</div>
              <div className="landing-hero">
                <div className="landing-copy">
                  <span className="eyebrow">FROM PAPER TO REPRODUCIBLE PIPELINE</span>
                  <h1>Make research<br /><span>reproducible.</span></h1>
                  <p>Ingest a paper and its code repository. Inspect the experiment graph, validate compute requirements, run the pipeline, and trace every result back to its evidence.</p>
                  <div className="landing-actions">
                    <button className="btn btn-primary btn-large" onClick={handleStartIngestion}>
                      <Plus size={17} /> Ingest a research paper
                    </button>
                    <button className="btn btn-secondary btn-large" onClick={handleQuickDemo} disabled={demoLoading}>
                      <Sparkles size={16} /> {demoLoading ? 'Preparing demo…' : 'Explore a quick demo'}
                    </button>
                  </div>
                  <div className="landing-footnote">
                    <span className={`status-dot ${backendOnline ? 'is-online' : 'is-offline'}`} />
                    {backendOnline ? 'Backend connected and ready for ingestion' : 'Connect to the API to ingest papers and create experiments'}
                  </div>
                </div>

                <div className="landing-visual" aria-label="Research workflow overview">
                  <div className="visual-grid" />
                  <div className="visual-index">RESEARCH PIPELINE <span>CG / 001</span></div>
                  <div className="workflow-stack">
                    <div className="workflow-card workflow-paper">
                      <span className="workflow-icon"><FileText size={17} /></span>
                      <div><span className="eyebrow">01 / SOURCE</span><strong>Research paper</strong><small>Claims · methods · conditions</small></div>
                      <ArrowUpRight size={15} className="workflow-arrow" />
                    </div>
                    <div className="workflow-connector"><span /></div>
                    <div className="workflow-card workflow-graph">
                      <span className="workflow-icon"><GitFork size={17} /></span>
                      <div><span className="eyebrow">02 / MODEL</span><strong>Experiment graph</strong><small>Code · data · dependencies</small></div>
                      <ArrowUpRight size={15} className="workflow-arrow" />
                    </div>
                    <div className="workflow-connector"><span /></div>
                    <div className="workflow-card workflow-run">
                      <span className="workflow-icon"><Play size={17} /></span>
                      <div><span className="eyebrow">03 / REPRODUCE</span><strong>Execution & evidence</strong><small>Runs · outputs · provenance</small></div>
                      <ArrowUpRight size={15} className="workflow-arrow" />
                    </div>
                  </div>
                  <div className="visual-footer"><span>TRACEABLE BY DESIGN</span><span>END-TO-END / 01—03</span></div>
                </div>
              </div>

              {notice && (
                <div className="app-notice" role="status">
                  <AlertTriangle size={16} /><span>{notice}</span>
                  <button onClick={() => setNotice('')} aria-label="Dismiss notice"><X size={15} /></button>
                </div>
              )}

              <div className="landing-bottom">
                <div className="landing-section-title">
                  <div><span className="eyebrow">WORKSPACE ENTRY</span><h2>Start with a source.</h2></div>
                  <span className="source-count">{experiments.length.toString().padStart(2, '0')} EXISTING EXPERIMENTS</span>
                </div>
                <div className="landing-options">
                  <button className="landing-option" onClick={handleStartIngestion}>
                    <span className="option-icon option-cyan"><UploadCloud size={19} /></span>
                    <span className="option-copy"><strong>Ingest a paper</strong><small>Extract research conditions and connect a code repository.</small></span>
                    <ArrowUpRight size={16} className="option-arrow" />
                  </button>
                  <button className="landing-option" onClick={handleQuickDemo} disabled={demoLoading}>
                    <span className="option-icon option-lime"><Sparkles size={19} /></span>
                    <span className="option-copy"><strong>{demoLoading ? 'Preparing demo…' : 'Launch quick demo'}</strong><small>Explore the workspace using a sample repository.</small></span>
                    <ArrowUpRight size={16} className="option-arrow" />
                  </button>
                  <button className="landing-option" onClick={loadExperiments} disabled={experimentsLoading}>
                    <span className="option-icon option-violet"><Search size={19} /></span>
                    <span className="option-copy"><strong>{experimentsLoading ? 'Checking experiments…' : 'Find existing experiments'}</strong><small>{experiments.length ? `${experiments.length} experiment${experiments.length === 1 ? '' : 's'} available in your workspace.` : 'Check the backend for experiments already created.'}</small></span>
                    <RefreshCw size={15} className={`option-arrow ${experimentsLoading ? 'is-spinning' : ''}`} />
                  </button>
                </div>
                {experiments.length > 0 && (
                  <div className="existing-experiments">
                    <div className="existing-heading"><span className="eyebrow">RECENT EXPERIMENTS</span><span>{experiments.length} AVAILABLE</span></div>
                    {experiments.slice(0, 4).map((experiment) => (
                      <button
                        className="existing-experiment-row"
                        key={experiment.experiment_id}
                        onClick={() => {
                          setSelectedExpId(experiment.experiment_id);
                          setActiveTab('ingest');
                        }}
                      >
                        <span className="existing-experiment-icon"><Database size={15} /></span>
                        <span className="existing-experiment-name"><strong>{getExperimentLabel(experiment)}</strong><small>{experiment.experiment_id}</small></span>
                        <ArrowUpRight size={15} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          <footer className="app-footer">
            <span><span className={`footer-status ${backendOnline ? 'is-online' : ''}`} /> CRISISGRID RESEARCH SYSTEM</span>
            <span>EXPERIMENT REPRODUCIBILITY <span className="footer-divider">/</span> BUILD 002</span>
          </footer>
        </main>
      </div>

      <IngestModal
        isOpen={showIngestModal}
        onClose={() => setShowIngestModal(false)}
        onIngested={async (newId) => {
          await loadExperiments();
          setSelectedExpId(newId);
          setActiveTab('ingest');
          setShowIngestModal(false);
        }}
      />
    </div>
  );
}

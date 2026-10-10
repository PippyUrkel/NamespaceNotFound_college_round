import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Box,
  Check,
  ChevronDown,
  CircleCheck,
  CircleX,
  Clipboard,
  Clock3,
  Cpu,
  Database,
  FileJson,
  Fingerprint,
  GitBranch,
  HardDrive,
  Info,
  Layers3,
  MemoryStick,
  PackageCheck,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from 'lucide-react';
import { api } from '../api';
import './EvidenceTab.css';

const formatDate = (value) => {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};

const formatDuration = (seconds) => {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—';
  const value = Number(seconds);
  if (value < 1) return `${value.toFixed(3)} s`;
  if (value < 60) return `${value.toFixed(1)} s`;
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
};

const formatBytesMb = (value) => {
  if (value == null || Number.isNaN(Number(value))) return 'Not recorded';
  return `${Number(value).toLocaleString()} MB`;
};

const humanize = (value) =>
  String(value || 'unknown')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase());

function StatusPill({ status, children }) {
  const normalized = String(status || '').toLowerCase();
  const tone =
    ['completed', 'success', 'passed', 'available', 'true'].includes(normalized)
      ? 'success'
      : ['failed', 'blocked', 'error', 'false', 'container_crash'].includes(normalized)
        ? 'danger'
        : ['warning', 'incomplete', 'partial', 'upstream_failure'].includes(normalized)
          ? 'warning'
          : 'neutral';

  return <span className={`evidence-status-pill is-${tone}`}>{children || humanize(status)}</span>;
}

function MetricCard({ icon: Icon, label, value, detail, tone = 'neutral', mono = false }) {
  return (
    <article className="evidence-summary-card">
      <div className="evidence-summary-card-top">
        <span className={`evidence-icon-box is-${tone}`}>
          <Icon size={16} strokeWidth={1.8} />
        </span>
        <span className="evidence-eyebrow">{label}</span>
      </div>
      <div className={`evidence-summary-value${mono ? ' is-mono' : ''}`}>{value ?? '—'}</div>
      {detail && <p className="evidence-summary-detail">{detail}</p>}
    </article>
  );
}

function SectionHeading({ icon: Icon, eyebrow, title, trailing }) {
  return (
    <div className="evidence-section-heading">
      <div className="evidence-section-heading-main">
        <span className="evidence-icon-box is-violet">
          <Icon size={17} strokeWidth={1.8} />
        </span>
        <div>
          <div className="evidence-eyebrow">{eyebrow}</div>
          <h3>{title}</h3>
        </div>
      </div>
      {trailing}
    </div>
  );
}

function DataRow({ label, value, mono = false }) {
  return (
    <div className="evidence-data-row">
      <span>{label}</span>
      <strong className={mono ? 'is-mono' : ''}>{value ?? '—'}</strong>
    </div>
  );
}

function SeedCard({ run }) {
  const seed = run?.seed ?? '—';
  const status = run?.status || 'unknown';
  const nodes = Object.values(run?.node_results || {});
  const failedNodes = nodes.filter((node) => node?.status === 'failed').length;
  const runtime = run?.runtime_seconds;
  const reason = run?.failure_reason || run?.failure_detail;

  return (
    <article className="evidence-seed-card">
      <div className="evidence-seed-main">
        <div className="evidence-seed-id">
          <span className="evidence-seed-label">SEED</span>
          <strong>{seed}</strong>
        </div>
        <div className="evidence-seed-description">
          <div className="evidence-seed-title">
            <span>Randomized execution</span>
            <StatusPill status={status} />
          </div>
          <p>{reason ? humanize(reason) : status === 'completed' ? 'Run completed' : 'No failure detail recorded'}</p>
        </div>
        <div className="evidence-seed-runtime">
          <span>RUNTIME</span>
          <strong>{formatDuration(runtime)}</strong>
        </div>
      </div>
      {failedNodes > 0 && (
        <div className="evidence-seed-footer">
          <AlertTriangle size={13} />
          {failedNodes} of {nodes.length} pipeline nodes marked failed
        </div>
      )}
      {run?.failure_detail && (
        <details className="evidence-seed-detail">
          <summary>View failure detail <ChevronDown size={13} /></summary>
          <p>{run.failure_detail}</p>
          {nodes.some((node) => node?.stderr) && (
            <pre>{nodes.filter((node) => node?.stderr).map((node) => `${node.node_id || 'Node'}: ${node.stderr}`).join('\n\n')}</pre>
          )}
        </details>
      )}
    </article>
  );
}

export default function EvidenceTab({ experimentId, latestExecution }) {
  const [evidence, setEvidence] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadEvidence() {
      if (!latestExecution?.execution_id) {
        setEvidence(null);
        setLoadError('');
        return;
      }

      setLoading(true);
      setLoadError('');
      try {
        const result = await api.getRunEvidence(experimentId, latestExecution.execution_id);
        if (!cancelled) setEvidence(result);
      } catch (error) {
        console.warn('Failed to load evidence:', error);
        if (!cancelled) {
          setEvidence(null);
          setLoadError('Evidence details could not be loaded. The execution manifest is still available below.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadEvidence();
    return () => {
      cancelled = true;
    };
  }, [experimentId, latestExecution?.execution_id]);

  const seedRuns = useMemo(
    () => Array.isArray(latestExecution?.seed_runs) ? latestExecution.seed_runs : [],
    [latestExecution?.seed_runs],
  );

  const config = latestExecution?.config || {};
  const hardware = latestExecution?.hardware || latestExecution?.feasibility?.resource_assessment || {};
  const feasibility = latestExecution?.feasibility || {};
  const limitations = evidence?.execution_limitations || [];
  const completedSeeds = evidence?.seeds_completed ?? seedRuns.filter((run) => run?.status === 'completed').length;
  const totalSeeds = evidence?.seeds_total ?? (config.seeds?.length || seedRuns.length);
  const allSeedsCompleted = evidence?.all_seeds_completed ?? (totalSeeds > 0 && completedSeeds === totalSeeds);
  const seedProgress = totalSeeds > 0 ? Math.min(100, (completedSeeds / totalSeeds) * 100) : 0;
  const dependencyChecks = latestExecution?.resolved_dependencies || feasibility?.dependency_checks || [];
  const datasetChecks = latestExecution?.dataset_identity || feasibility?.dataset_checks || [];
  const resourceRequirements = feasibility?.resource_requirements || [];
  const graphHash = latestExecution?.graph_hash;
  const dockerImage = latestExecution?.docker_image_digest || config.docker_image || 'Not recorded';

  async function copyManifest() {
    if (!latestExecution) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(latestExecution, null, 2));
      setCopied(true);
      setCopyError('');
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError('Clipboard access failed. Open the raw manifest and copy the JSON directly.');
    }
  }

  if (!latestExecution) {
    return (
      <div className="evidence-workspace">
        <section className="evidence-page-intro">
          <div>
            <div className="evidence-eyebrow">PROVENANCE / EXECUTION RECORD</div>
            <h2>Evidence <span>vault.</span></h2>
            <p>Inspect execution identity, environment conditions, and the evidence behind a research run.</p>
          </div>
          <div className="evidence-intro-mark"><Fingerprint size={28} /><span>CG / EVIDENCE</span></div>
        </section>
        <section className="evidence-empty-state">
          <span className="evidence-empty-icon"><FileJson size={24} /></span>
          <div className="evidence-eyebrow">NO EXECUTION MANIFEST</div>
          <h3>Your provenance record will appear here.</h3>
          <p>No execution has been recorded for this experiment yet. Launch a run in the Execution Runner tab to inspect its environment, seed outcomes, and provenance.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="evidence-workspace">
      <section className="evidence-page-intro">
        <div>
          <div className="evidence-eyebrow evidence-intro-kicker">
            <span className="evidence-live-dot" />
            PROVENANCE / EXECUTION RECORD
            {loading && <span className="evidence-refresh-label"><RefreshCw size={11} /> Updating evidence</span>}
          </div>
          <h2>Evidence <span>vault.</span></h2>
          <p>A visual record of the run's identity, execution environment, seed integrity, and recorded limitations.</p>
        </div>
        <div className="evidence-intro-mark"><Fingerprint size={28} /><span>CG / EVIDENCE</span></div>
      </section>

      {loadError && <div className="evidence-inline-notice is-warning"><Info size={15} />{loadError}</div>}

      <section className="evidence-summary-grid">
        <MetricCard
          icon={Fingerprint}
          label="Execution ID"
          value={latestExecution.execution_id}
          detail={`Created ${formatDate(latestExecution.created_at)}`}
          tone="cyan"
          mono
        />
        <MetricCard
          icon={GitBranch}
          label="Graph version & hash"
          value={<>{latestExecution.graph_version_id || '—'}{graphHash && <span className="evidence-value-secondary"> / {graphHash.slice(0, 12)}</span>}</>}
          detail="Fingerprint of the graph snapshot used for this run"
          tone="violet"
          mono
        />
        <MetricCard
          icon={Box}
          label="Container image"
          value={dockerImage}
          detail="Configured isolated execution environment"
          tone="cyan"
          mono
        />
        <article className="evidence-summary-card evidence-seed-summary">
          <div className="evidence-summary-card-top">
            <span className={`evidence-icon-box ${allSeedsCompleted ? 'is-success' : 'is-amber'}`}><Activity size={16} /></span>
            <span className="evidence-eyebrow">SEED EXECUTION INTEGRITY</span>
          </div>
          <div className="evidence-seed-summary-value"><strong>{completedSeeds}</strong><span>/ {totalSeeds}</span><StatusPill status={allSeedsCompleted ? 'completed' : 'incomplete'}>{allSeedsCompleted ? 'Complete' : 'Incomplete'}</StatusPill></div>
          <div className="evidence-progress-track"><span className={allSeedsCompleted ? 'is-complete' : ''} style={{ width: `${seedProgress}%` }} /></div>
          <p className="evidence-summary-detail">{allSeedsCompleted ? 'All configured seeds completed successfully.' : 'Incomplete runs must not be interpreted as a scientific verdict.'}</p>
        </article>
      </section>

      <section className="evidence-principle">
        <span className="evidence-principle-icon"><ShieldCheck size={18} /></span>
        <div>
          <div className="evidence-principle-heading">Execution status is not scientific validity</div>
          <p>Hardware limits, environment failures, or incomplete runs do not prove that a paper's claims are false. Evaluate scientific claims using completed runs and independent evidence.</p>
        </div>
        <span className="evidence-principle-tag">VALIDITY RULE / 001</span>
      </section>

      <section className="evidence-panel">
        <SectionHeading
          icon={Workflow}
          eyebrow="RUN TRACE"
          title="Seed execution results"
          trailing={<span className="evidence-section-count">{seedRuns.length || totalSeeds} runs recorded</span>}
        />
        {seedRuns.length ? (
          <div className="evidence-seed-list">{seedRuns.map((run, index) => <SeedCard key={`${run?.seed ?? index}`} run={run} />)}</div>
        ) : (
          <div className="evidence-compact-empty">Per-seed details were not included in this execution record. Configured seeds: {(config.seeds || []).join(', ') || 'Not recorded'}.</div>
        )}
      </section>

      <section className="evidence-detail-grid">
        <article className="evidence-panel">
          <SectionHeading icon={Cpu} eyebrow="HOST SNAPSHOT" title="Execution environment" />
          <div className="evidence-data-list">
            <DataRow label="CPU cores" value={hardware.cpu_cores ?? 'Not recorded'} />
            <DataRow label="Available RAM" value={formatBytesMb(hardware.ram_mb)} />
            <DataRow label="Available disk" value={formatBytesMb(hardware.disk_mb)} />
            <DataRow label="GPU" value={hardware.gpu_name || (hardware.gpu_available ? 'GPU available' : 'Not detected')} />
            <DataRow label="GPU memory" value={formatBytesMb(hardware.gpu_memory_mb)} />
            <DataRow label="Docker" value={hardware.docker_available == null ? 'Not recorded' : hardware.docker_available ? 'Available' : 'Unavailable'} />
            <DataRow label="Docker version" value={hardware.docker_version || 'Not recorded'} />
          </div>
        </article>

        <article className="evidence-panel">
          <SectionHeading icon={MemoryStick} eyebrow="RESOURCE ESTIMATE" title="Feasibility assessment" trailing={<StatusPill status={feasibility.verdict || 'not assessed'}>{humanize(feasibility.verdict || 'Not assessed')}</StatusPill>} />
          {feasibility.reasons?.length > 0 && (
            <div className="evidence-findings is-danger">
              {feasibility.reasons.map((reason, index) => <div key={`${reason}-${index}`}><CircleX size={14} /><span>{reason}</span></div>)}
            </div>
          )}
          {feasibility.warnings?.length > 0 && (
            <div className="evidence-findings is-warning">
              {feasibility.warnings.map((warning, index) => <div key={`${warning}-${index}`}><AlertTriangle size={14} /><span>{warning}</span></div>)}
            </div>
          )}
          <div className="evidence-data-list">
            <DataRow label="Estimated runtime" value={formatDuration(feasibility.estimated_total_runtime_seconds)} />
            <DataRow label="Execution timeout" value={config.execution_timeout_seconds != null ? `${config.execution_timeout_seconds}s` : 'Not recorded'} />
            <DataRow label="Default memory limit" value={config.default_memory_limit_mb != null ? formatBytesMb(config.default_memory_limit_mb) : 'Not recorded'} />
            <DataRow label="CPU limit" value={config.default_cpu_limit ?? 'Not recorded'} />
            <DataRow label="Last checked" value={formatDate(feasibility.checked_at)} />
          </div>
        </article>
      </section>

      <section className="evidence-detail-grid">
        <article className="evidence-panel">
          <SectionHeading icon={PackageCheck} eyebrow="DEPENDENCY AUDIT" title="Resolved packages" trailing={<span className="evidence-section-count">{dependencyChecks.length} packages</span>} />
          {dependencyChecks.length ? (
            <div className="evidence-check-list">
              {dependencyChecks.map((dependency, index) => (
                <div className="evidence-check-row" key={`${dependency.name}-${index}`}>
                  <span className={`evidence-check-icon ${dependency.available ? 'is-success' : 'is-danger'}`}>{dependency.available ? <CircleCheck size={15} /> : <CircleX size={15} />}</span>
                  <div className="evidence-check-name"><strong>{dependency.name}</strong><span>{dependency.required_version ? `Required ${dependency.required_version}` : 'Version not pinned'}</span></div>
                  <div className="evidence-check-value"><StatusPill status={dependency.available ? 'available' : 'failed'}>{dependency.available ? 'Available' : 'Missing'}</StatusPill><small>{dependency.installed_version || 'Version unknown'}</small></div>
                </div>
              ))}
            </div>
          ) : <div className="evidence-compact-empty">Dependency resolution details were not recorded.</div>}
        </article>

        <article className="evidence-panel">
          <SectionHeading icon={Database} eyebrow="DATASET IDENTITY" title="Dataset checks" trailing={<span className="evidence-section-count">{datasetChecks.length} datasets</span>} />
          {datasetChecks.length ? (
            <div className="evidence-check-list">
              {datasetChecks.map((dataset, index) => (
                <div className="evidence-check-row" key={`${dataset.name}-${index}`}>
                  <span className={`evidence-check-icon ${dataset.available ? 'is-success' : 'is-danger'}`}>{dataset.available ? <CircleCheck size={15} /> : <CircleX size={15} />}</span>
                  <div className="evidence-check-name"><strong>{dataset.name}</strong><span>{dataset.url || 'Dataset URL not recorded'}</span></div>
                  <div className="evidence-check-value"><StatusPill status={dataset.available ? 'available' : 'failed'}>{dataset.available ? 'Available' : 'Unavailable'}</StatusPill><small>{dataset.integrity_ok == null ? 'Integrity unverified' : dataset.integrity_ok ? 'Integrity verified' : 'Integrity mismatch'}</small></div>
                </div>
              ))}
            </div>
          ) : <div className="evidence-compact-empty">Dataset identity details were not recorded.</div>}
        </article>
      </section>

      {resourceRequirements.length > 0 && (
        <section className="evidence-panel">
          <SectionHeading icon={HardDrive} eyebrow="NODE-LEVEL ESTIMATES" title="Resource requirements" trailing={<span className="evidence-section-count">{resourceRequirements.length} nodes</span>} />
          <div className="evidence-table-wrap">
            <table className="evidence-resource-table">
              <thead><tr><th>Pipeline node</th><th>Estimated RAM</th><th>Estimated disk</th><th>GPU</th><th>Runtime</th></tr></thead>
              <tbody>{resourceRequirements.map((node) => (
                <tr key={node.node_id}>
                  <td className="is-mono">{node.node_id}</td>
                  <td>{formatBytesMb(node.estimated_ram_mb)}</td>
                  <td>{formatBytesMb(node.estimated_disk_mb)}</td>
                  <td><StatusPill status={node.requires_gpu ? 'warning' : 'neutral'}>{node.requires_gpu ? 'Required' : 'Not required'}</StatusPill></td>
                  <td>{formatDuration(node.estimated_runtime_seconds)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}

      {limitations.length > 0 && (
        <section className="evidence-panel">
          <SectionHeading icon={AlertTriangle} eyebrow="AUDITOR NOTES" title="Execution limitations" trailing={<span className="evidence-section-count is-amber">{limitations.length} recorded</span>} />
          <p className="evidence-section-description">These constraints describe the recorded execution context. They are not, by themselves, scientific verdicts.</p>
          <div className="evidence-limitations-list">
            {limitations.map((limitation, index) => (
              <article className="evidence-limitation" key={`${limitation.type}-${index}`}>
                <span className="evidence-limitation-icon"><AlertTriangle size={15} /></span>
                <div><strong>{humanize(limitation.type || 'Limitation')}</strong><p>{limitation.detail}</p></div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="evidence-panel evidence-raw-panel">
        <div className="evidence-raw-heading">
          <SectionHeading icon={FileJson} eyebrow="RAW PROVENANCE" title="Execution manifest" trailing={<span className="evidence-section-count">Read-only snapshot</span>} />
          <button className={`evidence-copy-btn${copied ? ' is-copied' : ''}`} onClick={copyManifest} type="button">
            {copied ? <Check size={14} /> : <Clipboard size={14} />}
            {copied ? 'Copied' : 'Copy manifest JSON'}
          </button>
        </div>
        <div className="evidence-raw-meta">
          <span><span className="evidence-meta-dot" /> JSON</span>
          <span>{Object.keys(latestExecution).length} top-level fields</span>
          <span>Execution {latestExecution.execution_id}</span>
        </div>
        {copyError && <p className="evidence-copy-error" role="alert">{copyError}</p>}
        <button className="evidence-raw-toggle" type="button" aria-expanded={rawOpen} onClick={() => setRawOpen((open) => !open)}>
          <span>{rawOpen ? 'Hide raw JSON' : 'View raw JSON'}</span>
          <ChevronDown size={15} className={rawOpen ? 'is-open' : ''} />
        </button>
        {rawOpen && <pre className="evidence-code-block"><code>{JSON.stringify(latestExecution, null, 2)}</code></pre>}
      </section>
      <footer className="evidence-footer">
        <span><span className="evidence-footer-dot" /> CRISISGRID RESEARCH SYSTEM</span>
        <span>PROVENANCE RECORD <b>/</b> {latestExecution.graph_version_id || 'UNVERSIONED'}</span>
      </footer>
    </div>
  );
}

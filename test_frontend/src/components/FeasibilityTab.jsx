import React from 'react';
import {
  Cpu,
  HardDrive,
  Server,
  Zap,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock3,
  Gauge,
  ShieldCheck,
  CircleHelp,
} from 'lucide-react';
import './FeasibilityTab.css';

const VERDICT_META = {
  feasible: {
    label: 'Feasible',
    tone: 'success',
    Icon: CheckCircle2,
    summary:
      'Host resources and container dependencies are fully sufficient to reproduce this experiment.',
  },
  feasible_with_limitations: {
    label: 'Feasible with limitations',
    tone: 'warning',
    Icon: AlertTriangle,
    summary:
      'Experiment can execute, but limitations exist (e.g. CPU-only execution or RAM bounds). Scientific parameters are preserved exactly and not altered.',
  },
  blocked: {
    label: 'Blocked',
    tone: 'danger',
    Icon: XCircle,
    summary:
      'Execution cannot proceed in isolated containers under current host conditions.',
  },
};

function formatMemory(mb) {
  return mb ? `${(mb / 1024).toFixed(1)} GB` : 'Unknown';
}

function ResourceCard({ icon: Icon, label, value, detail, tone = 'neutral' }) {
  return (
    <article className={`feasibility-resource feasibility-resource--${tone}`}>
      <div className="feasibility-resource__top">
        <span className="feasibility-resource__icon">
          <Icon size={17} strokeWidth={1.8} />
        </span>
        <span className="feasibility-resource__label">{label}</span>
      </div>
      <div className="feasibility-resource__value">{value}</div>
      {detail ? <div className="feasibility-resource__detail">{detail}</div> : null}
    </article>
  );
}

export default function FeasibilityTab({ feasibility }) {
  if (!feasibility) {
    return (
      <section className="feasibility-empty">
        <span className="feasibility-empty__icon">
          <CircleHelp size={22} strokeWidth={1.7} />
        </span>
        <p className="feasibility-eyebrow">FEASIBILITY / NO DATA</p>
        <h3>No assessment available</h3>
        <p>
          Run a feasibility assessment to inspect host capacity, container
          availability, and per-node resource estimates.
        </p>
      </section>
    );
  }

  const hw = feasibility.resource_assessment || {};
  const verdict = feasibility.verdict || 'feasible';
  const meta = VERDICT_META[verdict] || VERDICT_META.blocked;
  const VerdictIcon = meta.Icon;
  const reasons = Array.isArray(feasibility.reasons) ? feasibility.reasons : [];
  const warnings = Array.isArray(feasibility.warnings) ? feasibility.warnings : [];
  const requirements = Array.isArray(feasibility.resource_requirements)
    ? feasibility.resource_requirements
    : [];

  return (
    <div className="feasibility-workspace">
      <header className="feasibility-heading">
        <div>
          <p className="feasibility-eyebrow">EXECUTION PREFLIGHT / 01</p>
          <h2>Resource feasibility</h2>
          <p className="feasibility-heading__copy">
            Host capacity and runtime requirements for this experiment.
          </p>
        </div>
        <div className="feasibility-heading__stamp">
          <Gauge size={15} />
          <span>PRE-RUN CHECK</span>
        </div>
      </header>

      <section className={`feasibility-verdict feasibility-verdict--${meta.tone}`}>
        <div className="feasibility-verdict__mark">
          <VerdictIcon size={23} strokeWidth={1.8} />
        </div>
        <div className="feasibility-verdict__body">
          <div className="feasibility-verdict__title-row">
            <div>
              <p className="feasibility-eyebrow">ASSESSMENT RESULT</p>
              <h3>{meta.label}</h3>
            </div>
            <span className="feasibility-verdict__time">
              <Clock3 size={13} />
              {feasibility.checked_at
                ? new Date(feasibility.checked_at).toLocaleTimeString()
                : 'Assessed just now'}
            </span>
          </div>
          <p className="feasibility-verdict__summary">{meta.summary}</p>

          {reasons.length > 0 && (
            <div className="feasibility-notes feasibility-notes--danger">
              <h4><XCircle size={14} /> Blocking reasons</h4>
              <ul>
                {reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}
              </ul>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="feasibility-notes feasibility-notes--warning">
              <h4><AlertTriangle size={14} /> System warnings</h4>
              <ul>
                {warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}
              </ul>
            </div>
          )}
        </div>
      </section>

      <section className="feasibility-section">
        <div className="feasibility-section__heading">
          <div>
            <p className="feasibility-eyebrow">HOST ENVIRONMENT</p>
            <h3>Available resources</h3>
          </div>
          <span className="feasibility-section__count">05 CHECKS</span>
        </div>

        <div className="feasibility-resource-grid">
          <ResourceCard
            icon={Cpu}
            label="Host CPU"
            value={<>{hw.cpu_cores || 1}<span className="feasibility-unit"> cores</span></>}
            detail="Logical processing capacity"
            tone="cyan"
          />
          <ResourceCard
            icon={Server}
            label="Available RAM"
            value={formatMemory(hw.ram_mb)}
            detail={hw.ram_mb ? `${hw.ram_mb.toLocaleString()} MB detected` : 'Memory data unavailable'}
            tone="lime"
          />
          <ResourceCard
            icon={HardDrive}
            label="Free disk space"
            value={formatMemory(hw.disk_mb)}
            detail={hw.disk_mb ? `${hw.disk_mb.toLocaleString()} MB available` : 'Disk data unavailable'}
            tone="violet"
          />
          <ResourceCard
            icon={Zap}
            label="GPU acceleration"
            value={hw.gpu_available ? (hw.gpu_name || 'NVIDIA GPU') : 'CPU execution'}
            detail={
              hw.gpu_available
                ? (hw.gpu_memory_mb ? `${hw.gpu_memory_mb.toLocaleString()} MB VRAM` : 'GPU detected')
                : 'No compatible GPU detected'
            }
            tone={hw.gpu_available ? 'success' : 'warning'}
          />
          <ResourceCard
            icon={Server}
            label="Docker daemon"
            value={hw.docker_available ? 'Available' : 'Unavailable'}
            detail={hw.docker_version || 'Docker engine status'}
            tone={hw.docker_available ? 'success' : 'danger'}
          />
        </div>
      </section>

      {requirements.length > 0 && (
        <section className="feasibility-section feasibility-requirements">
          <div className="feasibility-section__heading">
            <div>
              <p className="feasibility-eyebrow">GRAPH / RESOURCE PROFILE</p>
              <h3>Per-node resource estimates</h3>
            </div>
            <div className="feasibility-runtime">
              <Clock3 size={14} />
              <span>Estimated runtime</span>
              <strong>~{feasibility.estimated_total_runtime_seconds || 0}s</strong>
            </div>
          </div>

          <div className="feasibility-table-wrap">
            <table className="feasibility-table">
              <thead>
                <tr>
                  <th>Node ID</th>
                  <th>Estimated RAM</th>
                  <th>Estimated disk</th>
                  <th>Compute</th>
                  <th>Est. runtime</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((req) => (
                  <tr key={req.node_id}>
                    <td>
                      <span className="feasibility-node-id">{req.node_id}</span>
                    </td>
                    <td>{req.estimated_ram_mb} <span className="feasibility-table__unit">MB</span></td>
                    <td>{req.estimated_disk_mb} <span className="feasibility-table__unit">MB</span></td>
                    <td>
                      <span className={`feasibility-chip ${req.requires_gpu ? 'feasibility-chip--gpu' : 'feasibility-chip--cpu'}`}>
                        <span className="feasibility-chip__dot" />
                        {req.requires_gpu ? 'GPU required' : 'CPU only'}
                      </span>
                    </td>
                    <td>{req.estimated_runtime_seconds}<span className="feasibility-table__unit">s</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="feasibility-table-footer">
            <ShieldCheck size={14} />
            <span>Estimates are advisory; scientific parameters remain unchanged.</span>
            <span className="feasibility-table-footer__count">{requirements.length} {requirements.length === 1 ? 'NODE' : 'NODES'}</span>
          </footer>
        </section>
      )}
    </div>
  );
}

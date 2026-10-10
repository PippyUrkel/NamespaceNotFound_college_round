
import React, { useEffect, useState } from 'react';
import {
  Play,
  RotateCcw,
  StopCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
  ShieldCheck,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Sparkles,
  Cpu,
  MemoryStick,
  Timer,
  GitBranch,
  Activity,
  X,
} from 'lucide-react';
import { api } from '../api';
import './RunnerTab.css';

function StatusPill({ status }) {
  const normalized = String(status || 'unknown').toLowerCase();

  const icon =
    normalized === 'completed' ? <CheckCircle2 size={12} /> :
    normalized === 'running' || normalized === 'preparing' ? <Activity size={12} /> :
    normalized === 'timed_out' ? <Clock size={12} /> :
    normalized === 'cancelled' ? <XCircle size={12} /> :
    normalized === 'resource_exhausted' ? <MemoryStick size={12} /> :
    normalized === 'failed' || normalized === 'partially_completed' ? <AlertCircle size={12} /> :
    <ShieldCheck size={12} />;

  return (
    <span className={`cg-runner-status is-${normalized.replace(/[^a-z0-9_-]/g, '-')}`}>
      {icon}
      {normalized.replaceAll('_', ' ')}
    </span>
  );
}

function MetricValue({ value, digits = 4 }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }

  return typeof value === 'number' ? value.toFixed(digits) : String(value);
}

export default function RunnerTab({
  experimentId,
  activeVersionId,
  latestExecution,
  onRefreshExecution,
}) {
  const [seedsInput, setSeedsInput] = useState('42, 123, 7');
  const [timeoutSec, setTimeoutSec] = useState('600');
  const [memMb, setMemMb] = useState('2048');
  const [cpuLimit, setCpuLimit] = useState('2.0');
  const [running, setRunning] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [expandedSeed, setExpandedSeed] = useState(null);
  const [selectedNodeLogs, setSelectedNodeLogs] = useState(null);
  const [progressEvents, setProgressEvents] = useState([]);
  const [actionError, setActionError] = useState('');

  const exec = latestExecution;

  const isActive = Boolean(
    exec &&
    (exec.status === 'running' || exec.status === 'preparing')
  );

  const parsedSeeds = seedsInput
    .split(',')
    .map((seed) => Number.parseInt(seed.trim(), 10))
    .filter((seed) => !Number.isNaN(seed));

  useEffect(() => {
    let interval = null;
    let cancelled = false;

    if (
      exec &&
      (
        exec.status === 'running' ||
        exec.status === 'preparing' ||
        running
      )
    ) {
      interval = window.setInterval(async () => {
        try {
          const events = await api.getProgress(
            experimentId,
            exec.execution_id
          );

          if (!cancelled) {
            setProgressEvents(events || []);
          }

          const updated = await api.getExecution(
            experimentId,
            exec.execution_id
          );

          if (
            !cancelled &&
            updated.status !== 'running' &&
            updated.status !== 'preparing'
          ) {
            setRunning(false);
            window.clearInterval(interval);
          }

          if (!cancelled) {
            onRefreshExecution();
          }
        } catch (error) {
          console.warn('Progress poll error:', error);
        }
      }, 2000);
    }

    return () => {
      cancelled = true;

      if (interval) {
        window.clearInterval(interval);
      }
    };
  }, [
    experimentId,
    exec?.execution_id,
    exec?.status,
    running,
    onRefreshExecution,
  ]);

  async function handleLaunch() {
    setActionError('');

    if (parsedSeeds.length === 0) {
      setActionError(
        'Enter at least one valid seed, separated by commas.'
      );
      return;
    }

    const timeout = Number.parseInt(timeoutSec, 10);
    const memory = Number.parseInt(memMb, 10);
    const cpu = Number.parseFloat(cpuLimit);

    if (!Number.isFinite(timeout) || timeout <= 0) {
      setActionError('Timeout must be a positive number of seconds.');
      return;
    }

    if (!Number.isFinite(memory) || memory <= 0) {
      setActionError('Memory limit must be a positive number of MB.');
      return;
    }

    if (!Number.isFinite(cpu) || cpu <= 0) {
      setActionError('CPU limit must be a positive number of cores.');
      return;
    }

    setRunning(true);
    setProgressEvents([]);

    try {
      const payload = {
        graph_version_id: activeVersionId || null,
        seeds: parsedSeeds,
        config_overrides: {
          default_timeout_seconds: timeout,
          default_memory_limit_mb: memory,
          default_cpu_limit: cpu,
        },
        skip_feasibility: false,
      };

      await api.submitExecution(experimentId, payload);
      onRefreshExecution();
    } catch (err) {
      setRunning(false);
      setActionError(
        `Execution launch failed: ${err?.message || 'Unknown error'}`
      );
    }
  }

  async function handleResume() {
    if (!exec) return;

    setActionError('');
    setResuming(true);

    try {
      await api.resumeExecution(
        experimentId,
        exec.execution_id,
        {
          retry_failed: true,
          additional_seeds: [],
        }
      );

      onRefreshExecution();
    } catch (err) {
      setActionError(
        `Resume failed: ${err?.message || 'Unknown error'}`
      );
    } finally {
      setResuming(false);
    }
  }

  async function handleCancel() {
    if (!exec) return;

    setActionError('');
    setCancelling(true);

    try {
      await api.cancelExecution(
        experimentId,
        exec.execution_id
      );

      onRefreshExecution();
    } catch (err) {
      setActionError(
        `Cancel failed: ${err?.message || 'Unknown error'}`
      );
    } finally {
      setCancelling(false);
    }
  }

  function openNodeLogs(nodeId, seed, nodeResult) {
    setSelectedNodeLogs({
      nodeId,
      seed,
      stdout: nodeResult.stdout,
      stderr: nodeResult.stderr,
    });
  }

  const seedRuns = exec?.seed_runs || [];

  const completedSeeds = seedRuns.filter(
    (seed) => seed.status === 'completed'
  ).length;

  const failedSeeds = seedRuns.filter((seed) =>
    ['failed', 'timed_out', 'resource_exhausted'].includes(
      seed.status
    )
  ).length;

  return (
    <div className="cg-runner">
      <section className="cg-runner-panel cg-runner-launch-panel">
        <div className="cg-runner-panel-head">
          <div className="cg-runner-title-group">
            <span className="cg-runner-icon-box">
              <Play size={18} />
            </span>

            <div>
              <div className="cg-runner-kicker">
                EXECUTION ENVIRONMENT / 01
              </div>

              <h2>Multi-seed execution</h2>

              <p>
                Run isolated experiment trials with controlled
                compute limits.
              </p>
            </div>
          </div>

          <div className="cg-runner-main-actions">
            {isActive && (
              <button
                type="button"
                className="cg-runner-button cg-runner-button-danger"
                onClick={handleCancel}
                disabled={cancelling}
              >
                {cancelling ? (
                  <Loader2 size={15} className="cg-runner-spin" />
                ) : (
                  <StopCircle size={15} />
                )}

                {cancelling ? 'Cancelling…' : 'Cancel run'}
              </button>
            )}

            {exec &&
              ['failed', 'partially_completed'].includes(exec.status) && (
                <button
                  type="button"
                  className="cg-runner-button cg-runner-button-secondary"
                  onClick={handleResume}
                  disabled={resuming}
                >
                  {resuming ? (
                    <Loader2 size={15} className="cg-runner-spin" />
                  ) : (
                    <RotateCcw size={15} />
                  )}

                  {resuming ? 'Resuming…' : 'Retry failed seeds'}
                </button>
              )}

            <button
              type="button"
              className="cg-runner-button cg-runner-button-primary"
              onClick={handleLaunch}
              disabled={running || isActive}
            >
              {running || isActive ? (
                <>
                  <Loader2 size={16} className="cg-runner-spin" />
                  Executing pipeline…
                </>
              ) : (
                <>
                  <Play size={15} fill="currentColor" />
                  Launch execution
                  {/* <Sparkles size={14} /> */}
                </>
              )}
            </button>
          </div>
        </div>

        {actionError && (
          <div className="cg-runner-alert" role="alert">
            <AlertCircle size={16} />

            <span>{actionError}</span>

            <button
              type="button"
              onClick={() => setActionError('')}
              aria-label="Dismiss message"
            >
              <X size={15} />
            </button>
          </div>
        )}

        <div className="cg-runner-config-grid">
          <div className="cg-runner-field cg-runner-seeds-field">
            <label htmlFor="cg-runner-seeds">
              Execution seeds
            </label>

            <div className="cg-runner-input-shell">
              <GitBranch size={15} />

              <input
                id="cg-runner-seeds"
                type="text"
                value={seedsInput}
                onChange={(event) =>
                  setSeedsInput(event.target.value)
                }
                placeholder="42, 123, 7"
                disabled={running || isActive}
              />
            </div>

            <small>
              {parsedSeeds.length} valid seed
              {parsedSeeds.length === 1 ? '' : 's'} detected
            </small>
          </div>

          <div className="cg-runner-field">
            <label htmlFor="cg-runner-timeout">
              Timeout per node
            </label>

            <div className="cg-runner-input-shell">
              <Timer size={15} />

              <input
                id="cg-runner-timeout"
                type="number"
                min="1"
                value={timeoutSec}
                onChange={(event) =>
                  setTimeoutSec(event.target.value)
                }
                disabled={running || isActive}
              />

              <span className="cg-runner-input-unit">SEC</span>
            </div>

            <small>Maximum runtime for each DAG node</small>
          </div>

          <div className="cg-runner-field">
            <label htmlFor="cg-runner-memory">
              Container memory
            </label>

            <div className="cg-runner-input-shell">
              <MemoryStick size={15} />

              <input
                id="cg-runner-memory"
                type="number"
                min="1"
                value={memMb}
                onChange={(event) =>
                  setMemMb(event.target.value)
                }
                disabled={running || isActive}
              />

              <span className="cg-runner-input-unit">MB</span>
            </div>

            <small>Memory cap per isolated container</small>
          </div>

          <div className="cg-runner-field">
            <label htmlFor="cg-runner-cpu">
              Container CPU limit
            </label>

            <div className="cg-runner-input-shell">
              <Cpu size={15} />

              <input
                id="cg-runner-cpu"
                type="number"
                min="0.1"
                step="0.1"
                value={cpuLimit}
                onChange={(event) =>
                  setCpuLimit(event.target.value)
                }
                disabled={running || isActive}
              />

              <span className="cg-runner-input-unit">CORES</span>
            </div>

            <small>Compute allocation per container</small>
          </div>
        </div>

        <div className="cg-runner-launch-foot">
          <div className="cg-runner-foot-note">
            <ShieldCheck size={15} />
            <span>
              Feasibility checks enabled before execution.
            </span>
          </div>

          <span className="cg-runner-mono">
            GRAPH REF: {activeVersionId || 'LATEST'}
          </span>
        </div>
      </section>

      {exec && (
        <section className="cg-runner-panel">
          <div className="cg-runner-panel-head cg-runner-exec-head">
            <div className="cg-runner-title-group">
              <span className="cg-runner-icon-box cg-runner-icon-cyan">
                <Activity size={18} />
              </span>

              <div>
                <div className="cg-runner-kicker">
                  RUN TELEMETRY / 02
                </div>

                <h2>Execution overview</h2>

                <p className="cg-runner-mono">
                  ID {exec.execution_id}
                </p>
              </div>
            </div>

            <StatusPill status={exec.status} />
          </div>

          <div className="cg-runner-exec-meta">
            <div className="cg-runner-meta-item">
              <span>GRAPH VERSION</span>
              <strong>{exec.graph_version_id || '—'}</strong>
            </div>

            <div className="cg-runner-meta-item">
              <span>GRAPH HASH</span>
              <strong className="cg-runner-mono">
                {exec.graph_hash?.slice(0, 12) || '—'}
              </strong>
            </div>

            <div className="cg-runner-meta-item">
              <span>TOTAL RUNTIME</span>
              <strong>
                {exec.total_runtime_seconds != null
                  ? `${exec.total_runtime_seconds.toFixed(2)}s`
                  : '—'}
              </strong>
            </div>

            <div className="cg-runner-meta-item">
              <span>SEEDS COMPLETED</span>
              <strong>
                {completedSeeds}
                <small> / {seedRuns.length}</small>
              </strong>
            </div>
          </div>

          {seedRuns.length > 0 && (
            <div
              className="cg-runner-progress-track"
              aria-label="Completed seeds progress"
            >
              <span
                style={{
                  width: `${Math.min(
                    100,
                    (completedSeeds / seedRuns.length) * 100
                  )}%`,
                }}
              />
            </div>
          )}

          {failedSeeds > 0 && (
            <div className="cg-runner-warning-line">
              <AlertCircle size={15} />

              <span>
                {failedSeeds} seed{failedSeeds === 1 ? '' : 's'}{' '}
                failed, timed out, or exhausted resources.
              </span>
            </div>
          )}

          {exec.error_summary && (
            <div className="cg-runner-alert">
              <AlertCircle size={16} />

              <span>
                <strong>Execution notice:</strong>{' '}
                {exec.error_summary}
              </span>
            </div>
          )}

          {exec.aggregated_metrics?.length > 0 && (
            <div className="cg-runner-data-section">
              <div className="cg-runner-subhead">
                <div>
                  <div className="cg-runner-kicker">
                    STATISTICAL SUMMARY
                  </div>

                  <h3>Aggregated scientific metrics</h3>
                </div>

                <span className="cg-runner-subhead-note">
                  Completed runs only
                </span>
              </div>

              <div className="cg-runner-table-wrap">
                <table className="cg-runner-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Mean</th>
                      <th>Std dev</th>
                      <th>Min</th>
                      <th>Max</th>
                      <th>Seeds</th>
                      <th>Integrity</th>
                    </tr>
                  </thead>

                  <tbody>
                    {exec.aggregated_metrics.map((metric) => (
                      <tr key={metric.metric_name}>
                        <td className="cg-runner-metric-name">
                          {metric.metric_name}
                        </td>

                        <td className="cg-runner-value">
                          <MetricValue value={metric.mean} />
                        </td>

                        <td className="cg-runner-value">
                          <MetricValue value={metric.std} />
                        </td>

                        <td className="cg-runner-value">
                          <MetricValue value={metric.min_val} />
                        </td>

                        <td className="cg-runner-value">
                          <MetricValue value={metric.max_val} />
                        </td>

                        <td>
                          {metric.num_completed} / {metric.num_total}
                        </td>

                        <td>
                          <span
                            className={`cg-runner-integrity ${
                              metric.is_complete
                                ? 'is-complete'
                                : 'is-incomplete'
                            }`}
                          >
                            {metric.is_complete
                              ? 'Complete'
                              : 'Incomplete'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {exec.aggregated_metrics.some(
                (metric) => !metric.is_complete
              ) && (
                <div className="cg-runner-stat-note">
                  <AlertCircle size={14} />
                  Incomplete runs are excluded, not treated as
                  zero-valued. Interpret these statistics with caution.
                </div>
              )}
            </div>
          )}

          <div className="cg-runner-data-section">
            <div className="cg-runner-subhead">
              <div>
                <div className="cg-runner-kicker">
                  INDEPENDENT TRIALS
                </div>

                <h3>
                  Seed execution records{' '}
                  <span className="cg-runner-count">
                    {seedRuns.length}
                  </span>
                </h3>
              </div>

              <span className="cg-runner-subhead-note">
                Select a seed to inspect its DAG nodes
              </span>
            </div>

            {seedRuns.length === 0 ? (
              <div className="cg-runner-empty">
                <Clock size={18} />
                <span>
                  Seed execution records will appear here when available.
                </span>
              </div>
            ) : (
              <div className="cg-runner-seed-list">
                {seedRuns.map((seedRun) => {
                  const isExpanded =
                    expandedSeed === seedRun.seed;

                  const metricValues = seedRun.metrics?.values
                    ? Object.entries(seedRun.metrics.values)
                    : [];

                  return (
                    <article
                      className={`cg-runner-seed${
                        isExpanded ? ' is-expanded' : ''
                      }`}
                      key={seedRun.seed}
                    >
                      <button
                        type="button"
                        className="cg-runner-seed-toggle"
                        onClick={() =>
                          setExpandedSeed(
                            isExpanded ? null : seedRun.seed
                          )
                        }
                        aria-expanded={isExpanded}
                      >
                        <span className="cg-runner-seed-chevron">
                          {isExpanded ? (
                            <ChevronDown size={16} />
                          ) : (
                            <ChevronRight size={16} />
                          )}
                        </span>

                        <span className="cg-runner-seed-name">
                          Seed {seedRun.seed}
                        </span>

                        <StatusPill status={seedRun.status} />

                        {seedRun.failure_reason &&
                          seedRun.failure_reason !== 'none' && (
                            <span className="cg-runner-failure-reason">
                              {seedRun.failure_reason}
                            </span>
                          )}

                        <span className="cg-runner-seed-metrics">
                          {metricValues.map(([key, value]) => (
                            <span key={key}>
                              {key}:{' '}
                              {typeof value === 'number'
                                ? value.toFixed(3)
                                : String(value)}
                            </span>
                          ))}
                        </span>

                        <span className="cg-runner-seed-runtime">
                          {seedRun.runtime_seconds != null
                            ? `${seedRun.runtime_seconds.toFixed(2)}s`
                            : '—'}
                        </span>
                      </button>

                      {isExpanded && seedRun.node_results && (
                        <div className="cg-runner-node-area">
                          <div className="cg-runner-node-area-label">
                            DAG NODE BREAKDOWN
                            <span>SEED {seedRun.seed}</span>
                          </div>

                          <div className="cg-runner-node-grid">
                            {Object.entries(seedRun.node_results).map(
                              ([nodeId, nodeResult]) => (
                                <div
                                  className="cg-runner-node-card"
                                  key={nodeId}
                                >
                                  <div className="cg-runner-node-head">
                                    <strong>{nodeId}</strong>
                                    <StatusPill
                                      status={nodeResult.status}
                                    />
                                  </div>

                                  <div className="cg-runner-node-meta">
                                    <span>
                                      Exit code:{' '}
                                      {nodeResult.exit_code ?? '—'}
                                    </span>

                                    <span>
                                      {nodeResult.runtime_seconds != null
                                        ? `${nodeResult.runtime_seconds.toFixed(2)}s`
                                        : '—'}
                                    </span>
                                  </div>

                                  <div className="cg-runner-node-foot">
                                    {nodeResult.cache_hit && (
                                      <span className="cg-runner-cache">
                                        CACHE HIT
                                      </span>
                                    )}

                                    {(nodeResult.stdout ||
                                      nodeResult.stderr) && (
                                      <button
                                        type="button"
                                        className="cg-runner-log-button"
                                        onClick={() =>
                                          openNodeLogs(
                                            nodeId,
                                            seedRun.seed,
                                            nodeResult
                                          )
                                        }
                                      >
                                        <Terminal size={13} />
                                        View logs
                                      </button>
                                    )}
                                  </div>
                                </div>
                              )
                            )}
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      )}

      {progressEvents.length > 0 && (
        <section className="cg-runner-panel cg-runner-events-panel">
          <div className="cg-runner-panel-head cg-runner-events-head">
            <div className="cg-runner-title-group">
              <span className="cg-runner-icon-box cg-runner-icon-cyan">
                <Terminal size={18} />
              </span>

              <div>
                <div className="cg-runner-kicker">
                  LIVE TELEMETRY / 03
                </div>

                <h2>Execution event stream</h2>
              </div>
            </div>

            <span className="cg-runner-event-count">
              {progressEvents.length} EVENTS
            </span>
          </div>

          <div className="cg-runner-terminal">
            {progressEvents.map((event, index) => {
              const type = String(
                event.event_type || 'event'
              ).toLowerCase();

              const eventClass = type.includes('fail')
                ? 'is-failure'
                : type.includes('hit')
                  ? 'is-cache'
                  : 'is-info';

              return (
                <div
                  className="cg-runner-event"
                  key={`${event.timestamp}-${index}`}
                >
                  <time>
                    {event.timestamp
                      ? new Date(event.timestamp).toLocaleTimeString()
                      : '--:--:--'}
                  </time>

                  <span
                    className={`cg-runner-event-type ${eventClass}`}
                  >
                    {event.event_type || 'event'}
                  </span>

                  <span className="cg-runner-event-message">
                    {event.message}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {selectedNodeLogs && (
        <div
          className="cg-runner-log-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedNodeLogs(null);
            }
          }}
        >
          <section
            className="cg-runner-log-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cg-runner-log-title"
          >
            <header className="cg-runner-log-header">
              <div className="cg-runner-title-group">
                <span className="cg-runner-icon-box cg-runner-icon-cyan">
                  <Terminal size={17} />
                </span>

                <div>
                  <div className="cg-runner-kicker">NODE OUTPUT</div>

                  <h2 id="cg-runner-log-title">
                    {selectedNodeLogs.nodeId}
                    <span> · Seed {selectedNodeLogs.seed}</span>
                  </h2>
                </div>
              </div>

              <button
                type="button"
                className="cg-runner-close"
                onClick={() => setSelectedNodeLogs(null)}
                aria-label="Close logs"
              >
                <X size={17} />
              </button>
            </header>

            <div className="cg-runner-log-content">
              {selectedNodeLogs.stdout && (
                <div className="cg-runner-log-block">
                  <div className="cg-runner-log-label is-stdout">
                    STDOUT
                  </div>

                  <pre>{selectedNodeLogs.stdout}</pre>
                </div>
              )}

              {selectedNodeLogs.stderr && (
                <div className="cg-runner-log-block">
                  <div className="cg-runner-log-label is-stderr">
                    STDERR
                  </div>

                  <pre className="is-stderr">
                    {selectedNodeLogs.stderr}
                  </pre>
                </div>
              )}
            </div>

            <footer className="cg-runner-log-footer">
              <button
                type="button"
                className="cg-runner-button cg-runner-button-secondary"
                onClick={() => setSelectedNodeLogs(null)}
              >
                Close logs
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { 
  Play, RotateCcw, StopCircle, CheckCircle2, XCircle, Clock, 
  Terminal, ShieldCheck, AlertCircle, ChevronDown, ChevronRight, Loader2, Sparkles
} from 'lucide-react';
import { api } from '../api';

export default function RunnerTab({ 
  experimentId, 
  activeVersionId, 
  latestExecution, 
  onRefreshExecution 
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

  const exec = latestExecution;

  // Poll progress if execution is running
  useEffect(() => {
    let interval = null;
    if (exec && (exec.status === 'running' || exec.status === 'preparing' || running)) {
      interval = setInterval(async () => {
        try {
          const events = await api.getProgress(experimentId, exec.execution_id);
          setProgressEvents(events || []);
          const updated = await api.getExecution(experimentId, exec.execution_id);
          if (updated.status !== 'running' && updated.status !== 'preparing') {
            setRunning(false);
            clearInterval(interval);
          }
          onRefreshExecution();
        } catch (e) {
          console.warn('Progress poll error:', e);
        }
      }, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [exec?.execution_id, exec?.status, running]);

  async function handleLaunch() {
    setRunning(true);
    setProgressEvents([]);
    try {
      const parsedSeeds = seedsInput
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));

      const payload = {
        graph_version_id: activeVersionId || null,
        seeds: parsedSeeds.length > 0 ? parsedSeeds : [42, 123, 7],
        config_overrides: {
          default_timeout_seconds: parseInt(timeoutSec, 10) || 600,
          default_memory_limit_mb: parseInt(memMb, 10) || 2048,
          default_cpu_limit: parseFloat(cpuLimit) || 2.0,
        },
        skip_feasibility: false,
      };

      const res = await api.submitExecution(experimentId, payload);
      onRefreshExecution();
    } catch (err) {
      alert('Execution launch failed: ' + err.message);
    } finally {
      setRunning(false);
    }
  }

  async function handleResume() {
    if (!exec) return;
    setResuming(true);
    try {
      await api.resumeExecution(experimentId, exec.execution_id, {
        retry_failed: true,
        additional_seeds: [],
      });
      onRefreshExecution();
    } catch (err) {
      alert('Resume failed: ' + err.message);
    } finally {
      setResuming(false);
    }
  }

  async function handleCancel() {
    if (!exec) return;
    setCancelling(true);
    try {
      await api.cancelExecution(experimentId, exec.execution_id);
      onRefreshExecution();
    } catch (err) {
      alert('Cancel failed: ' + err.message);
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Execution Launch Controls */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h4 style={{ fontSize: '1rem', fontWeight: 600 }}>Multi-Seed Execution Controls</h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Runs each seed in an isolated Docker container with multi-framework determinism.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.6rem' }}>
            {exec && exec.status === 'running' && (
              <button className="btn btn-danger btn-sm" onClick={handleCancel} disabled={cancelling}>
                <StopCircle size={14} /> Cancel Run
              </button>
            )}
            {exec && (exec.status === 'failed' || exec.status === 'partially_completed') && (
              <button className="btn btn-secondary btn-sm" onClick={handleResume} disabled={resuming}>
                <RotateCcw size={14} /> Retry / Resume Failed Seeds
              </button>
            )}
            <button className="btn btn-primary" onClick={handleLaunch} disabled={running}>
              {running ? (
                <>
                  <Loader2 size={16} className="spin" /> Executing Pipeline...
                </>
              ) : (
                <>
                  <Play size={16} /> Launch Multi-Seed Execution
                </>
              )}
            </button>
          </div>
        </div>

        {/* Configuration Inputs */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
              Execution Seeds (Comma-separated)
            </label>
            <input
              type="text"
              className="input"
              style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
              value={seedsInput}
              onChange={(e) => setSeedsInput(e.target.value)}
              placeholder="42, 123, 7"
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
              Timeout per Node (seconds)
            </label>
            <input
              type="number"
              className="input"
              style={{ width: '100%' }}
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(e.target.value)}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
              Container RAM Limit (MB)
            </label>
            <input
              type="number"
              className="input"
              style={{ width: '100%' }}
              value={memMb}
              onChange={(e) => setMemMb(e.target.value)}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
              Container CPU Limit (Cores)
            </label>
            <input
              type="text"
              className="input"
              style={{ width: '100%' }}
              value={cpuLimit}
              onChange={(e) => setCpuLimit(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Active Execution Status Banner */}
      {exec && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span className={`badge ${
                exec.status === 'completed' ? 'badge-green' :
                exec.status === 'running' ? 'badge-blue' :
                exec.status === 'failed' ? 'badge-red' :
                exec.status === 'timed_out' ? 'badge-amber' : 'badge-gray'
              }`}>
                {exec.status}
              </span>
              <strong style={{ fontSize: '0.95rem' }}>Execution: {exec.execution_id}</strong>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                Graph {exec.graph_version_id} ({exec.graph_hash?.slice(0, 8)})
              </span>
            </div>

            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Total Runtime: <strong style={{ color: 'var(--text-main)' }}>{exec.total_runtime_seconds?.toFixed(2) || '—'}s</strong>
            </div>
          </div>

          {exec.error_summary && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '0.375rem',
              padding: '0.75rem',
              color: '#f87171',
              fontSize: '0.8rem',
            }}>
              <strong>Execution Notice:</strong> {exec.error_summary}
            </div>
          )}

          {/* Aggregated Scientific Metrics */}
          {exec.aggregated_metrics && exec.aggregated_metrics.length > 0 && (
            <div>
              <h5 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                Aggregated Scientific Metrics (Valid Completed Runs Only)
              </h5>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', fontSize: '0.825rem', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                      <th style={{ padding: '0.5rem' }}>Metric</th>
                      <th style={{ padding: '0.5rem' }}>Mean</th>
                      <th style={{ padding: '0.5rem' }}>Std Dev</th>
                      <th style={{ padding: '0.5rem' }}>Min</th>
                      <th style={{ padding: '0.5rem' }}>Max</th>
                      <th style={{ padding: '0.5rem' }}>Completed Seeds</th>
                      <th style={{ padding: '0.5rem' }}>Integrity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exec.aggregated_metrics.map((m) => (
                      <tr key={m.metric_name} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                        <td style={{ padding: '0.5rem', fontWeight: 600 }}>{m.metric_name}</td>
                        <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                          {m.mean !== null ? m.mean.toFixed(4) : '—'}
                        </td>
                        <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>
                          {m.std !== null ? m.std.toFixed(4) : '—'}
                        </td>
                        <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>{m.min_val ?? '—'}</td>
                        <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>{m.max_val ?? '—'}</td>
                        <td style={{ padding: '0.5rem' }}>{m.num_completed} / {m.num_total}</td>
                        <td style={{ padding: '0.5rem' }}>
                          <span className={`badge ${m.is_complete ? 'badge-green' : 'badge-amber'}`}>
                            {m.is_complete ? 'Complete' : 'Incomplete Sample'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {exec.aggregated_metrics.some((m) => !m.is_complete) && (
                <p style={{ fontSize: '0.75rem', color: '#fbbf24', marginTop: '0.5rem' }}>
                  ⚠️ Incomplete runs are excluded and never treated as zero-valued. Interpret incomplete statistics with caution.
                </p>
              )}
            </div>
          )}

          {/* Per-Seed Independent Runs */}
          <div>
            <h5 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.65rem', color: 'var(--text-muted)' }}>
              Independent Seed Execution Records ({exec.seed_runs?.length || 0})
            </h5>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {(exec.seed_runs || []).map((sr) => {
                const isExpanded = expandedSeed === sr.seed;
                return (
                  <div key={sr.seed} style={{
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border)',
                    borderRadius: '0.5rem',
                    overflow: 'hidden',
                  }}>
                    <div 
                      onClick={() => setExpandedSeed(isExpanded ? null : sr.seed)}
                      style={{
                        padding: '0.75rem 1rem',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                        background: isExpanded ? 'rgba(255, 255, 255, 0.04)' : 'transparent',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <strong style={{ fontSize: '0.9rem', fontFamily: 'var(--font-mono)' }}>Seed {sr.seed}</strong>
                        <span className={`badge ${
                          sr.status === 'completed' ? 'badge-green' :
                          sr.status === 'running' ? 'badge-blue' :
                          sr.status === 'timed_out' ? 'badge-amber' :
                          sr.status === 'resource_exhausted' ? 'badge-purple' : 'badge-red'
                        }`}>
                          {sr.status}
                        </span>
                        {sr.failure_reason && sr.failure_reason !== 'none' && (
                          <span style={{ fontSize: '0.75rem', color: '#f87171' }}>
                            ({sr.failure_reason})
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.8rem' }}>
                        {sr.metrics?.values && Object.entries(sr.metrics.values).map(([mk, mv]) => (
                          <span key={mk} style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                            {mk}: {typeof mv === 'number' ? mv.toFixed(3) : String(mv)}
                          </span>
                        ))}
                        <span style={{ color: 'var(--text-dim)' }}>
                          {sr.runtime_seconds !== null ? `${sr.runtime_seconds.toFixed(2)}s` : '—'}
                        </span>
                      </div>
                    </div>

                    {/* Node Breakdown for Expanded Seed */}
                    {isExpanded && sr.node_results && (
                      <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid var(--border)' }}>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem', fontWeight: 600 }}>
                          DAG Node Breakdown for Seed {sr.seed}:
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '0.5rem' }}>
                          {Object.entries(sr.node_results).map(([nid, nr]) => (
                            <div key={nid} style={{
                              background: 'rgba(0, 0, 0, 0.3)',
                              border: '1px solid var(--border)',
                              borderRadius: '0.375rem',
                              padding: '0.6rem',
                              fontSize: '0.775rem',
                            }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem' }}>
                                <strong style={{ color: '#e2e8f0' }}>{nid}</strong>
                                <span className={`badge ${
                                  nr.status === 'completed' ? 'badge-green' :
                                  nr.status === 'timed_out' ? 'badge-amber' : 'badge-red'
                                }`}>
                                  {nr.status}
                                </span>
                              </div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-dim)', fontSize: '0.725rem' }}>
                                <span>Exit code: {nr.exit_code ?? '—'}</span>
                                {nr.cache_hit && <span className="badge badge-purple btn-sm">Cache Hit</span>}
                                <span>{nr.runtime_seconds?.toFixed(2) || '0'}s</span>
                              </div>
                              {(nr.stdout || nr.stderr) && (
                                <button 
                                  className="btn btn-secondary btn-sm"
                                  style={{ marginTop: '0.4rem', width: '100%', fontSize: '0.7rem' }}
                                  onClick={() => setSelectedNodeLogs({ nodeId: nid, seed: sr.seed, stdout: nr.stdout, stderr: nr.stderr })}
                                >
                                  <Terminal size={12} /> View Logs
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Live Progress Event Stream */}
      {progressEvents.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h5 style={{ fontSize: '0.85rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Terminal size={14} color="var(--accent-cyan)" /> Live Execution Event Log
            </h5>
            <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)' }}>{progressEvents.length} events</span>
          </div>

          <div className="terminal">
            {progressEvents.map((evt, idx) => (
              <div key={idx} style={{ marginBottom: '0.2rem' }}>
                <span style={{ color: 'var(--text-dim)' }}>[{new Date(evt.timestamp).toLocaleTimeString()}]</span>{' '}
                <span style={{ color: evt.event_type.includes('fail') ? '#f87171' : evt.event_type.includes('hit') ? '#c084fc' : '#38bdf8' }}>
                  {evt.event_type}:
                </span>{' '}
                <span>{evt.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Node Log Viewer Modal */}
      {selectedNodeLogs && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Terminal size={18} color="var(--accent-blue)" />
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                  Logs: {selectedNodeLogs.nodeId} (Seed {selectedNodeLogs.seed})
                </h4>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setSelectedNodeLogs(null)}>✕</button>
            </div>
            <div className="modal-body">
              {selectedNodeLogs.stdout && (
                <div style={{ marginBottom: '0.75rem' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#34d399', marginBottom: '0.3rem' }}>STDOUT</div>
                  <pre className="terminal" style={{ maxHeight: '200px' }}>{selectedNodeLogs.stdout}</pre>
                </div>
              )}
              {selectedNodeLogs.stderr && (
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#f87171', marginBottom: '0.3rem' }}>STDERR</div>
                  <pre className="terminal" style={{ maxHeight: '200px', color: '#fca5a5' }}>{selectedNodeLogs.stderr}</pre>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setSelectedNodeLogs(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

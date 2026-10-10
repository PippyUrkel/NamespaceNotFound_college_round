import React, { useState, useEffect } from 'react';
import {
  ShieldAlert, ShieldCheck, FileText, Play, RefreshCw, Download,
  CheckCircle2, XCircle, HelpCircle, AlertTriangle, Scale,
} from 'lucide-react';
import { api } from '../api';

const VERDICT_STYLES = {
  'Reproducible': { color: '#34d399', bg: 'rgba(16, 185, 129, 0.1)', border: 'rgba(16, 185, 129, 0.3)', Icon: CheckCircle2 },
  'Not reproducible': { color: '#f87171', bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.3)', Icon: XCircle },
  'Not verifiable': { color: '#fbbf24', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.3)', Icon: HelpCircle },
  'Pending verification': { color: '#93c5fd', bg: 'rgba(59, 130, 246, 0.08)', border: 'rgba(59, 130, 246, 0.25)', Icon: HelpCircle },
};

const CLAIM_BADGES = {
  reproducible: ['badge-green', 'Reproducible'],
  not_reproducible: ['badge-red', 'Not reproducible'],
  not_verifiable: ['badge-amber', 'Not verifiable'],
};

const SEVERITY_BADGES = { critical: 'badge-red', high: 'badge-amber', medium: 'badge-purple', low: 'badge-gray' };
const RISK_COLORS = { low: '#34d399', medium: '#fbbf24', high: '#f87171' };

function fmt(value, digits = 4) {
  if (value === null || value === undefined) return '—';
  return String(parseFloat(Number(value).toPrecision(digits)));
}

function evidenceLabel(ev) {
  const where = [ev.section, ev.file_path, ev.page_number ? `page ${ev.page_number}` : null, ev.url].filter(Boolean).join(', ');
  return `${ev.source}${where ? ` (${where})` : ''}`;
}

export default function AuditTab({ experimentId, latestExecution }) {
  const [audit, setAudit] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [includeLlm, setIncludeLlm] = useState(true);

  useEffect(() => {
    setAudit(null);
    setReport(null);
    setError('');
    loadAll();
  }, [experimentId]);

  async function loadAll() {
    try {
      setAudit(await api.getAudit(experimentId));
    } catch (e) {
      setAudit(null);
    }
    try {
      setReport(await api.getReport(experimentId));
    } catch (e) {
      setReport(null);
    }
  }

  async function run(label, action) {
    setBusy(label);
    setError('');
    try {
      await action();
      await loadAll();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  const verification = audit?.claim_verification || report?.claim_verification;
  const verdict = report?.verdict;
  const verdictStyle = VERDICT_STYLES[verdict?.status] || VERDICT_STYLES['Pending verification'];
  const findings = report?.findings || audit?.findings || [];
  const risk = report?.risk_score || audit?.risk_score;
  const auditedExecution = audit?.run?.execution_id;
  const runAuditStale = latestExecution && auditedExecution !== latestExecution.execution_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Actions */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
        <button className="btn btn-secondary btn-sm" disabled={!!busy}
          onClick={() => run('static', () => api.runStaticAudit(experimentId, includeLlm))}>
          <ShieldAlert size={14} /> {busy === 'static' ? 'Auditing...' : 'Run Static Audit'}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <input type="checkbox" checked={includeLlm} onChange={(e) => setIncludeLlm(e.target.checked)} />
          include LLM checks (background)
        </label>

        <button className="btn btn-secondary btn-sm" disabled={!!busy || !latestExecution}
          title={latestExecution ? '' : 'Run the experiment in the Execution Runner tab first'}
          onClick={() => run('run', () => api.runRunAudit(experimentId, latestExecution?.execution_id))}>
          <Play size={14} /> {busy === 'run' ? 'Comparing...' : 'Compare Latest Run vs Paper'}
        </button>

        <button className="btn btn-primary btn-sm" disabled={!!busy}
          onClick={() => run('report', () => api.generateReport(experimentId))}>
          <FileText size={14} /> {busy === 'report' ? 'Generating...' : 'Generate Report'}
        </button>

        <button className="btn btn-secondary btn-sm" disabled={!!busy} onClick={() => run('refresh', loadAll)}>
          <RefreshCw size={13} />
        </button>

        {report && (
          <a className="btn btn-secondary btn-sm" href={api.getReportMarkdownUrl(experimentId)} target="_blank" rel="noreferrer">
            <Download size={14} /> report.md
          </a>
        )}

        {runAuditStale && (
          <span className="badge badge-amber">
            <AlertTriangle size={12} /> Latest run {latestExecution.execution_id} not yet compared with the paper
          </span>
        )}
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#f87171', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {/* Verdict */}
      {verdict ? (
        <div style={{
          background: verdictStyle.bg, border: `1px solid ${verdictStyle.border}`, borderRadius: '0.75rem',
          padding: '1.25rem', display: 'flex', gap: '1rem', alignItems: 'flex-start',
        }}>
          <verdictStyle.Icon size={24} color={verdictStyle.color} style={{ marginTop: '0.1rem' }} />
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: verdictStyle.color, marginBottom: '0.35rem' }}>
              Verdict: {verdict.status}
            </h3>
            <ul style={{ fontSize: '0.85rem', color: 'var(--text-muted)', paddingLeft: '1.1rem', lineHeight: 1.6 }}>
              {verdict.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.5rem' }}>
              Report generated {new Date(report.generated_at).toLocaleString()}
            </div>
          </div>
        </div>
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
          No report yet. Click <strong>Generate Report</strong>: it runs the static audit and compares the latest execution with the paper's claims.
        </div>
      )}

      {/* Claim verification */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <Scale size={18} color="var(--accent-cyan)" />
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Paper Claims vs Reproduced Results</h4>
          {verification && (
            <span className="badge badge-blue">tolerance ±{Math.round((verification.tolerance || 0.1) * 100)}%</span>
          )}
        </div>

        {!verification ? (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Not compared yet. Run the experiment, then click <strong>Compare Latest Run vs Paper</strong>.
          </p>
        ) : verification.claims.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{verification.reasons.join(' ')}</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--text-dim)', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '0.5rem' }}>Metric</th>
                  <th style={{ padding: '0.5rem' }}>Claimed (paper)</th>
                  <th style={{ padding: '0.5rem' }}>Reproduced (mean ± std)</th>
                  <th style={{ padding: '0.5rem' }}>Gap</th>
                  <th style={{ padding: '0.5rem' }}>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {verification.claims.map((c, i) => {
                  const [badge, label] = CLAIM_BADGES[c.verdict] || CLAIM_BADGES.not_verifiable;
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border)', verticalAlign: 'top' }}>
                      <td style={{ padding: '0.5rem', fontWeight: 600 }}>
                        {c.metric}
                        {c.claim_quote && (
                          <div style={{ fontWeight: 400, fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic', maxWidth: '360px' }}>
                            “{c.claim_quote}”
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>{fmt(c.claimed_value)}</td>
                      <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>
                        {fmt(c.reproduced_mean)}{c.reproduced_std != null ? ` ± ${fmt(c.reproduced_std, 2)}` : ''}
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>{c.seeds_run} seed(s)</div>
                      </td>
                      <td style={{ padding: '0.5rem', fontFamily: 'var(--font-mono)' }}>
                        {c.gap != null ? `${(c.gap * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        <span className={`badge ${badge}`}>{label}</span>
                        {c.used_assumed_values && (
                          <div style={{ fontSize: '0.72rem', color: '#fbbf24', marginTop: '0.25rem' }}>run used assumed values</div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Risk score + findings */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
          <ShieldCheck size={18} color="var(--accent-purple)" />
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Reproducibility Audit Findings</h4>
          {risk && (
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: RISK_COLORS[risk.bucket] }}>
              Risk {risk.score}/100 ({risk.bucket})
            </span>
          )}
        </div>

        {!audit && !report ? (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No audit has been run.</p>
        ) : findings.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No findings.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {findings.map((f, i) => (
              <div key={i} style={{ background: 'rgba(255, 255, 255, 0.03)', borderRadius: '0.5rem', padding: '0.75rem 0.9rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
                  <span className={`badge ${SEVERITY_BADGES[f.severity] || 'badge-gray'}`}>{f.severity}</span>
                  <span className="badge badge-gray">{f.status}</span>
                  <span className="badge badge-gray">{f.phase}</span>
                  <strong style={{ fontSize: '0.875rem' }}>{f.title}</strong>
                </div>
                <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{f.message}</p>
                {f.evidence?.length > 0 && (
                  <ul style={{ fontSize: '0.75rem', color: 'var(--text-dim)', paddingLeft: '1.1rem', marginTop: '0.35rem' }}>
                    {f.evidence.map((ev, j) => (
                      <li key={j}>
                        <em>{evidenceLabel(ev)}</em>{ev.exact_text ? `: “${ev.exact_text.slice(0, 200)}”` : ''}
                      </li>
                    ))}
                  </ul>
                )}
                {f.remediation && (
                  <div style={{ fontSize: '0.775rem', color: '#93c5fd', marginTop: '0.35rem' }}>Remediation: {f.remediation}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Limitations */}
      {report?.limitations?.length > 0 && (
        <div className="card">
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>Limitations of this report</h4>
          <ul style={{ fontSize: '0.825rem', color: 'var(--text-muted)', paddingLeft: '1.1rem', lineHeight: 1.6 }}>
            {report.limitations.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

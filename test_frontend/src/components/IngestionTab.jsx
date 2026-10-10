import React from 'react';
import { FileText, GitBranch, Database, ShieldAlert, CheckCircle2, AlertTriangle, Layers } from 'lucide-react';

export default function IngestionTab({ spec, conditionProvenance, discrepancies }) {
  if (!spec) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No ingestion specification loaded.
      </div>
    );
  }

  const paper = spec.paper || {};
  const repo = spec.repo || {};
  const conditions = conditionProvenance || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
            <FileText size={18} color="var(--accent-blue)" />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Research Paper Details</h4>
          </div>
          <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <div><strong style={{ color: 'var(--text-muted)' }}>Title:</strong> {spec.title || paper.title || 'Untitled'}</div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Dataset:</strong> {spec.dataset || 'Not specified'}</div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Status:</strong> <span className="badge badge-green">{spec.status || 'ingested'}</span></div>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
            <GitBranch size={18} color="var(--accent-indigo)" />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Code Repository</h4>
          </div>
          <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <strong style={{ color: 'var(--text-muted)' }}>Repo:</strong> {repo.repository_url || spec.repository_url || 'No repo attached'}
            </div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Branch / Ref:</strong> {repo.branch || 'main'} ({repo.commit_sha ? repo.commit_sha.slice(0, 7) : 'head'})</div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Files Found:</strong> {repo.files ? Object.keys(repo.files).length : 0} python files</div>
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
            <Database size={18} color="var(--accent-cyan)" />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Pinecone Vector Index</h4>
          </div>
          <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <div><strong style={{ color: 'var(--text-muted)' }}>Index:</strong> bnb (aws / us-east-1)</div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Indexed Chunks:</strong> {spec.vector_indexed ? 'Indexed' : 'Indexed (Local Fallback)'}</div>
            <div><strong style={{ color: 'var(--text-muted)' }}>Feasibility:</strong> {spec.validation?.feasibility || 'Feasible'}</div>
          </div>
        </div>
      </div>

      {/* Discrepancy Warnings */}
      {discrepancies && discrepancies.length > 0 && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: '0.5rem',
          padding: '1rem',
          color: '#fbbf24',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', fontWeight: 600 }}>
            <ShieldAlert size={18} />
            <span>Paper vs Repository Discrepancies Detected ({discrepancies.length})</span>
          </div>
          <ul style={{ listStyleType: 'disc', paddingLeft: '1.5rem', fontSize: '0.85rem' }}>
            {discrepancies.map((d, i) => (
              <li key={i}>{typeof d === 'string' ? d : `${d.field}: Paper says "${d.paper_value}", repo says "${d.repo_value}"`}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Condition Reconciliation Table */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Layers size={18} color="var(--accent-purple)" />
            <h4 style={{ fontSize: '1rem', fontWeight: 600 }}>Scientific Conditions & Provenance Reconciliation</h4>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Strict evidence tracking per field</span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.825rem', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.6rem' }}>Parameter</th>
                <th style={{ padding: '0.6rem' }}>Reconciled Value</th>
                <th style={{ padding: '0.6rem' }}>Source</th>
                <th style={{ padding: '0.6rem' }}>Confidence</th>
                <th style={{ padding: '0.6rem' }}>Status</th>
                <th style={{ padding: '0.6rem' }}>Evidence Snippet</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(conditions).length > 0 ? (
                Object.entries(conditions).map(([key, cond]) => {
                  const val = typeof cond === 'object' ? cond.value : cond;
                  const src = typeof cond === 'object' ? cond.source : 'reconciled';
                  const conf = typeof cond === 'object' ? cond.confidence : 0.9;
                  const isAssumed = typeof cond === 'object' ? cond.is_assumed : false;
                  const hasDiscrepancy = typeof cond === 'object' ? cond.discrepancy : false;
                  const evidence = typeof cond === 'object' ? cond.evidence : null;

                  return (
                    <tr key={key} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <td style={{ padding: '0.6rem', fontWeight: 600, color: '#e2e8f0' }}>{key}</td>
                      <td style={{ padding: '0.6rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                        {Array.isArray(val) ? val.join(', ') : String(val ?? 'None')}
                      </td>
                      <td style={{ padding: '0.6rem' }}>
                        <span className={`badge ${
                          src === 'paper' ? 'badge-blue' :
                          src === 'repository' ? 'badge-purple' :
                          src === 'tuned' ? 'badge-green' :
                          src === 'assumed' ? 'badge-amber' : 'badge-gray'
                        }`}>
                          {src}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem' }}>{Math.round(conf * 100)}%</td>
                      <td style={{ padding: '0.6rem' }}>
                        {isAssumed ? (
                          <span className="badge badge-amber" title="Assumed standard ML default value">Assumed</span>
                        ) : hasDiscrepancy ? (
                          <span className="badge badge-red" title="Paper and code mismatch">Discrepancy</span>
                        ) : (
                          <span className="badge badge-green">Verified</span>
                        )}
                      </td>
                      <td style={{ padding: '0.6rem', color: 'var(--text-dim)', maxWidth: '320px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {evidence || '—'}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-dim)' }}>
                    No condition provenance records available.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Raw Paper Claims */}
      {paper.claims && paper.claims.length > 0 && (
        <div className="card">
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.75rem' }}>Extracted Paper Claims</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {paper.claims.map((claim, idx) => (
              <div key={idx} style={{
                background: 'rgba(255, 255, 255, 0.03)',
                padding: '0.65rem 0.85rem',
                borderRadius: '0.375rem',
                fontSize: '0.825rem',
                display: 'flex',
                justifyContent: 'space-between',
              }}>
                <span>{claim.text || JSON.stringify(claim)}</span>
                {claim.confidence && <span className="badge badge-blue">{Math.round(claim.confidence * 100)}% conf</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

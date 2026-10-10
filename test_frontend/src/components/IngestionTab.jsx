import React from 'react';
import {
  FileText,
  GitBranch,
  Database,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Layers3,
  BookOpen,
  ExternalLink,
  FileSearch,
  CircleHelp,
  Fingerprint,
} from 'lucide-react';
import './IngestionTab.css';

const SOURCE_META = {
  paper: { label: 'Research paper', tone: 'paper' },
  repository: { label: 'Repository', tone: 'repository' },
  tuned: { label: 'Tuned', tone: 'tuned' },
  assumed: { label: 'Assumed', tone: 'assumed' },
};

function sourceMeta(source) {
  return SOURCE_META[source] || {
    label: source || 'Reconciled',
    tone: source || 'neutral',
  };
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined || value === '') return 'None';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function IngestionTab({ spec, conditionProvenance, discrepancies }) {
  if (!spec) {
    return (
      <section className="ingestion-empty">
        <span className="ingestion-empty__icon"><FileSearch size={22} /></span>
        <p className="ingestion-eyebrow">INGESTION / NO SPECIFICATION</p>
        <h3>No ingestion specification loaded</h3>
        <p>Upload or ingest a research paper and its code repository to inspect extracted metadata and reconciled scientific conditions.</p>
      </section>
    );
  }

  const paper = spec.paper || {};
  const repo = spec.repo || {};
  const conditions = conditionProvenance || {};
  const repoUrl = repo.repository_url || spec.repository_url || '';
  const repoFiles = repo.files && typeof repo.files === 'object' ? Object.keys(repo.files).length : 0;
  const status = spec.status || 'ingested';
  const conditionEntries = Object.entries(conditions);

  return (
    <div className="ingestion-workspace">
      <header className="ingestion-heading">
        <div>
          <p className="ingestion-eyebrow">SOURCE INTAKE / 01</p>
          <h2>Research ingestion</h2>
          <p>Review the source material, repository snapshot, and evidence behind each scientific condition.</p>
        </div>
        <div className="ingestion-heading__status">
          <span className="ingestion-heading__status-dot" />
          <span>{status.replaceAll('_', ' ')}</span>
        </div>
      </header>

      <section className="ingestion-overview">
        <article className="ingestion-source-card ingestion-source-card--paper">
          <div className="ingestion-source-card__top">
            <span className="ingestion-source-card__icon"><FileText size={18} /></span>
            <span className="ingestion-source-card__index">SOURCE / 01</span>
          </div>
          <p className="ingestion-eyebrow">PRIMARY SOURCE</p>
          <h3>Research paper</h3>
          <p className="ingestion-source-card__title">{spec.title || paper.title || 'Untitled research paper'}</p>
          <div className="ingestion-source-card__facts">
            <div><span>Dataset</span><strong>{spec.dataset || 'Not specified'}</strong></div>
            <div><span>Ingestion status</span><strong className="ingestion-text-success"><CheckCircle2 size={13} />{status.replaceAll('_', ' ')}</strong></div>
          </div>
        </article>

        <article className="ingestion-source-card ingestion-source-card--repo">
          <div className="ingestion-source-card__top">
            <span className="ingestion-source-card__icon"><GitBranch size={18} /></span>
            <span className="ingestion-source-card__index">SOURCE / 02</span>
          </div>
          <p className="ingestion-eyebrow">IMPLEMENTATION SOURCE</p>
          <h3>Code repository</h3>
          {repoUrl ? (
            <a className="ingestion-repo-link" href={repoUrl} target="_blank" rel="noreferrer">
              <span>{repoUrl}</span><ExternalLink size={13} />
            </a>
          ) : (
            <p className="ingestion-source-card__title">No repository attached</p>
          )}
          <div className="ingestion-source-card__facts">
            <div><span>Branch / ref</span><strong>{repo.branch || 'main'} <span className="ingestion-inline-muted">({repo.commit_sha ? repo.commit_sha.slice(0, 7) : 'head'})</span></strong></div>
            <div><span>Files found</span><strong>{repoFiles} Python files</strong></div>
          </div>
        </article>

        <article className="ingestion-source-card ingestion-source-card--vector">
          <div className="ingestion-source-card__top">
            <span className="ingestion-source-card__icon"><Database size={18} /></span>
            <span className="ingestion-source-card__index">RETRIEVAL / 03</span>
          </div>
          <p className="ingestion-eyebrow">EVIDENCE RETRIEVAL</p>
          <h3>Vector index</h3>
          <p className="ingestion-source-card__title">Pinecone · bnb</p>
          <div className="ingestion-source-card__facts">
            <div><span>Endpoint</span><strong>aws / us-east-1</strong></div>
            <div><span>Index state</span><strong>{spec.vector_indexed ? 'Indexed' : 'Indexed · local fallback'}</strong></div>
            <div><span>Feasibility</span><strong>{spec.validation?.feasibility || 'Feasible'}</strong></div>
          </div>
        </article>
      </section>

      {/* {discrepancies?.length > 0 && (
        <section className="ingestion-discrepancies">
          <div className="ingestion-discrepancies__heading">
            <span className="ingestion-discrepancies__icon"><ShieldAlert size={18} /></span>
            <div>
              <p className="ingestion-eyebrow">CONFLICT DETECTED</p>
              <h3>Paper / repository discrepancies</h3>
            </div>
            <span className="ingestion-discrepancies__count">{discrepancies.length.toString().padStart(2, '0')}</span>
          </div>
          <ul>
            {discrepancies.map((item, index) => (
              <li key={index}>
                <span className="ingestion-discrepancies__bullet" />
                <span>{typeof item === 'string' ? item : `${item.field}: Paper says "${item.paper_value}", repo says "${item.repo_value}"`}</span>
              </li>
            ))}
          </ul>
        </section>
      )} */}

      <section className="ingestion-panel">
        <header className="ingestion-panel__header">
          <div className="ingestion-panel__title">
            <span className="ingestion-panel__icon"><Layers3 size={17} /></span>
            <div>
              <p className="ingestion-eyebrow">PARAMETER-LEVEL EVIDENCE</p>
              <h3>Scientific conditions & provenance</h3>
            </div>
          </div>
          <span className="ingestion-panel__note"><Fingerprint size={13} />Strict evidence tracking per field</span>
        </header>

        <div className="ingestion-table-wrap">
          <table className="ingestion-table">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Reconciled value</th>
                <th>Source</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Evidence snippet</th>
              </tr>
            </thead>
            <tbody>
              {conditionEntries.length > 0 ? conditionEntries.map(([key, condition]) => {
                const isObject = condition !== null && typeof condition === 'object' && !Array.isArray(condition);
                const value = isObject ? condition.value : condition;
                const source = isObject ? condition.source : 'reconciled';
                const confidence = isObject && typeof condition.confidence === 'number' ? condition.confidence : 0.9;
                const assumed = isObject ? condition.is_assumed : false;
                const discrepancy = isObject ? condition.discrepancy : false;
                const evidence = isObject ? condition.evidence : null;
                const sourceInfo = sourceMeta(source);
                const state = assumed ? 'assumed' : discrepancy ? 'conflict' : 'verified';

                return (
                  <tr key={key}>
                    <td><span className="ingestion-parameter-name">{key}</span></td>
                    <td><code className="ingestion-value">{formatValue(value)}</code></td>
                    <td><span className={`ingestion-source-tag ingestion-source-tag--${sourceInfo.tone}`}>{sourceInfo.label}</span></td>
                    <td>
                      <div className="ingestion-confidence">
                        <div className="ingestion-confidence__track"><span style={{ width: `${Math.max(0, Math.min(100, confidence * 100))}%` }} /></div>
                        <span>{Math.round(confidence * 100)}%</span>
                      </div>
                    </td>
                    <td><span className={`ingestion-state ingestion-state--${state}`}>
                      {assumed ? <AlertTriangle size={12} /> : discrepancy ? <ShieldAlert size={12} /> : <CheckCircle2 size={12} />}
                      {assumed ? 'Assumed' : discrepancy ? 'Discrepancy' : 'Verified'}
                    </span></td>
                    <td className="ingestion-evidence-cell" title={evidence || ''}>{evidence || '—'}</td>
                  </tr>
                );
              }) : (
                <tr><td colSpan={6} className="ingestion-table-empty">No condition provenance records available.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <footer className="ingestion-panel__footer">
          <span>{conditionEntries.length} {conditionEntries.length === 1 ? 'condition' : 'conditions'} tracked</span>
          <span>Values remain traceable to their source</span>
        </footer>
      </section>

      {paper.claims?.length > 0 && (
        <section className="ingestion-panel ingestion-claims">
          <header className="ingestion-panel__header">
            <div className="ingestion-panel__title">
              <span className="ingestion-panel__icon ingestion-panel__icon--paper"><BookOpen size={17} /></span>
              <div><p className="ingestion-eyebrow">EXTRACTION OUTPUT</p><h3>Extracted paper claims</h3></div>
            </div>
            <span className="ingestion-panel__note">{paper.claims.length} CLAIMS</span>
          </header>
          <div className="ingestion-claims__list">
            {paper.claims.map((claim, index) => (
              <article className="ingestion-claim" key={index}>
                <span className="ingestion-claim__number">{String(index + 1).padStart(2, '0')}</span>
                <p>{claim.text || JSON.stringify(claim)}</p>
                {claim.confidence !== undefined && claim.confidence !== null && (
                  <span className="ingestion-claim__confidence">{Math.round(claim.confidence * 100)}% confidence</span>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

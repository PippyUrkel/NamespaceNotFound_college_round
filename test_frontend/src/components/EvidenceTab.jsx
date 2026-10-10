
import React, { useState, useEffect } from 'react';
import {
  ShieldCheck, FileCheck, Copy, Check, Info, Box, Layers,
  Fingerprint, Activity, AlertTriangle,
} from 'lucide-react';
import { api } from '../api';
import './EvidenceTab.css';

function ManifestCard({ icon: Icon, label, value, detail, tone = 'neutral', mono = false }) {
  return (
    <article className="evidence-metric-card">
      <div className="evidence-metric-top">
        <span className={`evidence-metric-icon evidence-tone-${tone}`}>
          <Icon size={16} />
        </span>
        <span className="evidence-eyebrow">{label}</span>
      </div>
      <div className={`evidence-metric-value ${mono ? 'evidence-mono' : ''}`}>
        {value}
      </div>
      {detail && <div className="evidence-metric-detail">{detail}</div>}
    </article>
  );
}

export default function EvidenceTab({ experimentId, latestExecution }) {
  const [evidence, setEvidence] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [copyError, setCopyError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadEvidence() {
      if (!latestExecution?.execution_id) {
        setEvidence(null);
        return;
      }

      setLoading(true);
      setCopyError('');

      try {
        const data = await api.getRunEvidence(
          experimentId,
          latestExecution.execution_id
        );
        if (!cancelled) setEvidence(data);
      } catch (error) {
        console.warn('Failed to load evidence:', error);
        if (!cancelled) setEvidence(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadEvidence();

    return () => {
      cancelled = true;
    };
  }, [experimentId, latestExecution?.execution_id]);

  async function copyManifest() {
    if (!latestExecution) return;

    try {
      await navigator.clipboard.writeText(
        JSON.stringify(latestExecution, null, 2)
      );
      setCopied(true);
      setCopyError('');
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError(
        'Clipboard access failed. Copy the JSON directly from the manifest below.'
      );
    }
  }

  if (!latestExecution) {
    return (
      <div className="evidence-workspace">
        <section className="evidence-intro">
          <div>
            <div className="evidence-eyebrow">
              PROVENANCE / EXECUTION RECORD
            </div>
            <h2>Evidence <span>vault.</span></h2>
            <p>
              Inspect immutable execution metadata and the evidence
              supporting a run.
            </p>
          </div>

          <div className="evidence-intro-mark">
            <Fingerprint size={28} />
            <span>CG / EVIDENCE</span>
          </div>
        </section>

        <section className="evidence-empty-state">
          <span className="evidence-empty-icon">
            <FileCheck size={25} />
          </span>

          <div className="evidence-eyebrow">NO EXECUTION MANIFEST</div>

          <h3>Your provenance record will appear here.</h3>

          <p>
            No execution manifest has been recorded yet. Launch an execution
            run in the Execution Runner tab to inspect its provenance evidence.
          </p>
        </section>
      </div>
    );
  }

  const seedsCompleted = evidence?.seeds_completed ?? 0;
  const seedsTotal = evidence?.seeds_total ?? 0;
  const allSeedsCompleted = Boolean(evidence?.all_seeds_completed);

  const seedProgress =
    seedsTotal > 0
      ? Math.min(100, (seedsCompleted / seedsTotal) * 100)
      : 0;

  return (
    <div className="evidence-workspace">
      <section className="evidence-intro">
        <div>
          <div className="evidence-eyebrow evidence-intro-kicker">
            <span className="evidence-live-dot" />
            PROVENANCE / EXECUTION RECORD
          </div>

          <h2>Evidence <span>vault.</span></h2>

          <p>
            Inspect the execution fingerprint, environment, and recorded
            limitations behind this experiment.
          </p>
        </div>

        <div className="evidence-intro-mark">
          <Fingerprint size={28} />
          <span>CG / EVIDENCE</span>
        </div>
      </section>

      <section className="evidence-principle">
        <span className="evidence-principle-icon">
          <Info size={19} />
        </span>

        <div>
          <div className="evidence-principle-heading">
            Execution status ≠ scientific validity
          </div>

          <p>
            Hardware bounds, container resource exhaustion, or incomplete runs
            do <strong>not</strong> automatically imply that a research paper’s
            scientific claims are false. Scientific claims must be evaluated
            independently using rigorous evidence.
          </p>
        </div>

        <span className="evidence-principle-tag">
          VALIDITY RULE / 001
        </span>
      </section>

      <section className="evidence-metrics-grid">
        <ManifestCard
          icon={Fingerprint}
          label="Execution ID"
          value={latestExecution.execution_id}
          detail={
            latestExecution.created_at
              ? `Created ${new Date(
                  latestExecution.created_at
                ).toLocaleString()}`
              : 'Creation timestamp unavailable'
          }
          mono
          tone="research"
        />

        <ManifestCard
          icon={Layers}
          label="Graph version & hash"
          value={
            <>
              {latestExecution.graph_version_id || '—'}
              <span className="evidence-value-secondary">
                {latestExecution.graph_hash
                  ? ` / ${latestExecution.graph_hash.slice(0, 8)}`
                  : ''}
              </span>
            </>
          }
          detail="Immutable graph snapshot"
          mono
          tone="code"
        />

        <ManifestCard
          icon={Box}
          label="Docker image digest"
          value={
            latestExecution.docker_image_digest ||
            latestExecution.config?.docker_image ||
            'python:3.11-slim'
          }
          detail="Isolated sandbox environment"
          mono
          tone="research"
        />

        <article className="evidence-metric-card">
          <div className="evidence-metric-top">
            <span
              className={`evidence-metric-icon ${
                allSeedsCompleted
                  ? 'evidence-tone-success'
                  : 'evidence-tone-assumed'
              }`}
            >
              <Activity size={16} />
            </span>

            <span className="evidence-eyebrow">
              SEED EXECUTION INTEGRITY
            </span>
          </div>

          <div className="evidence-seed-value">
            <strong>{seedsCompleted}</strong>
            <span>/ {seedsTotal}</span>
          </div>

          <div className="evidence-seed-track">
            <span
              className={allSeedsCompleted ? 'evidence-seed-complete' : ''}
              style={{ width: `${seedProgress}%` }}
            />
          </div>

          <div
            className={`evidence-metric-detail ${
              allSeedsCompleted
                ? 'evidence-text-success'
                : 'evidence-text-assumed'
            }`}
          >
            {allSeedsCompleted
              ? 'All seeds completed'
              : 'Incomplete runs'}

            {loading ? ' · Refreshing evidence…' : ''}
          </div>
        </article>
      </section>

      {evidence?.execution_limitations?.length > 0 && (
        <section className="evidence-panel">
          <div className="evidence-section-heading">
            <div className="evidence-section-heading-main">
              <span className="evidence-section-icon evidence-tone-assumed">
                <ShieldCheck size={17} />
              </span>

              <div>
                <div className="evidence-eyebrow">AUDITOR NOTES</div>
                <h3>Execution limitations</h3>
              </div>
            </div>

            <span className="evidence-count-chip">
              {evidence.execution_limitations.length} recorded
            </span>
          </div>

          <p className="evidence-section-description">
            Constraints recorded for review. These limitations describe the
            execution context and are not, by themselves, scientific verdicts.
          </p>

          <div className="evidence-limitations-list">
            {evidence.execution_limitations.map((limitation, index) => (
              <article
                className="evidence-limitation"
                key={`${limitation.type}-${index}`}
              >
                <span className="evidence-limitation-icon">
                  <AlertTriangle size={15} />
                </span>

                <div>
                  <strong>
                    {(limitation.type || 'limitation').replace(/_/g, ' ')}
                  </strong>
                  <p>{limitation.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="evidence-panel evidence-manifest-panel">
        <div className="evidence-section-heading">
          <div className="evidence-section-heading-main">
            <span className="evidence-section-icon evidence-tone-code">
              <FileCheck size={17} />
            </span>

            <div>
              <div className="evidence-eyebrow">RAW PROVENANCE</div>
              <h3>Execution manifest</h3>
            </div>
          </div>

          <button
            className={`evidence-copy-btn ${copied ? 'is-copied' : ''}`}
            onClick={copyManifest}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy manifest JSON'}
          </button>
        </div>

        <div className="evidence-manifest-meta">
          <span>
            <span className="evidence-meta-dot" />
            JSON
          </span>
          <span>READ-ONLY SNAPSHOT</span>
          <span>
            {Object.keys(latestExecution).length} top-level fields
          </span>
        </div>

        {copyError && (
          <p className="evidence-copy-error" role="alert">
            {copyError}
          </p>
        )}

        <pre className="evidence-code-block">
          <code>{JSON.stringify(latestExecution, null, 2)}</code>
        </pre>
      </section>
    </div>
  );
}

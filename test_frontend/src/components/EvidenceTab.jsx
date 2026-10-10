import React, { useState, useEffect } from 'react';
import { ShieldCheck, FileCheck, Copy, Check, Info, Box, Layers } from 'lucide-react';
import { api } from '../api';

export default function EvidenceTab({ experimentId, latestExecution }) {
  const [evidence, setEvidence] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (latestExecution?.execution_id) {
      loadEvidence();
    }
  }, [latestExecution?.execution_id]);

  async function loadEvidence() {
    setLoading(true);
    try {
      const data = await api.getRunEvidence(experimentId, latestExecution.execution_id);
      setEvidence(data);
    } catch (e) {
      console.warn('Failed to load evidence:', e);
    } finally {
      setLoading(false);
    }
  }

  function copyManifest() {
    if (latestExecution) {
      navigator.clipboard.writeText(JSON.stringify(latestExecution, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  if (!latestExecution) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No execution manifest recorded yet. Launch an execution run to inspect provenance evidence.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Scientific Verdict Notice */}
      <div style={{
        background: 'rgba(59, 130, 246, 0.08)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        borderRadius: '0.75rem',
        padding: '1.25rem',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '1rem',
      }}>
        <Info size={22} color="var(--accent-blue)" style={{ marginTop: '0.1rem' }} />
        <div>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#93c5fd', marginBottom: '0.25rem' }}>
            Strict Separation of Execution Status and Scientific Validity
          </h4>
          <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            In CrisisGrid, execution status is strictly decoupled from scientific verdicts. Hardware bounds, container resource exhaustion, or incomplete runs do <strong>not</strong> automatically imply that a research paper’s scientific claims are false. Scientific claims are evaluated only on rigorous evidence.
          </p>
        </div>
      </div>

      {/* Manifest Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
        <div className="card">
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: '0.3rem' }}>
            Execution ID
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {latestExecution.execution_id}
          </div>
          <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
            Created {new Date(latestExecution.created_at).toLocaleString()}
          </span>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: '0.3rem' }}>
            Graph Version & Hash
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent-indigo)' }}>
            {latestExecution.graph_version_id} ({latestExecution.graph_hash?.slice(0, 8)})
          </div>
          <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>Immutable graph snapshot</span>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: '0.3rem' }}>
            Docker Image Digest
          </div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {latestExecution.docker_image_digest || latestExecution.config?.docker_image || 'python:3.11-slim'}
          </div>
          <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>Isolated sandbox environment</span>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: '0.3rem' }}>
            Seed Execution Integrity
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700 }}>
            {evidence?.seeds_completed ?? 0} / {evidence?.seeds_total ?? 0}{' '}
            <span style={{ fontSize: '0.8rem', color: evidence?.all_seeds_completed ? '#34d399' : '#fbbf24' }}>
              ({evidence?.all_seeds_completed ? 'All Completed' : 'Incomplete Runs'})
            </span>
          </div>
          <span style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>Multi-seed independent trials</span>
        </div>
      </div>

      {/* Audit Evidence Limitations List */}
      {evidence?.execution_limitations && evidence.execution_limitations.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <ShieldCheck size={18} color="var(--accent-amber)" />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Execution Limitations Recorded for Auditor</h4>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {evidence.execution_limitations.map((lim, idx) => (
              <div key={idx} style={{
                background: 'rgba(255, 255, 255, 0.03)',
                padding: '0.65rem 0.85rem',
                borderRadius: '0.375rem',
                fontSize: '0.825rem',
              }}>
                <strong style={{ color: '#fbbf24', textTransform: 'capitalize' }}>{lim.type.replace(/_/g, ' ')}: </strong>
                <span>{lim.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Raw JSON Manifest Inspector */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileCheck size={18} color="var(--accent-purple)" />
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Execution Manifest (JSON Provenance Record)</h4>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={copyManifest}>
            {copied ? <Check size={14} color="#34d399" /> : <Copy size={14} />}
            <span>{copied ? 'Copied' : 'Copy Manifest JSON'}</span>
          </button>
        </div>

        <pre className="code-block" style={{ maxHeight: '350px' }}>
          {JSON.stringify(latestExecution, null, 2)}
        </pre>
      </div>
    </div>
  );
}

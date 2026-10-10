import React, { useState } from 'react';
import { X, UploadCloud, GitBranch, AlertCircle, Loader2 } from 'lucide-react';
import { api } from '../api';

export default function IngestModal({ isOpen, onClose, onIngested }) {
  const [file, setFile] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file && !repoUrl.trim()) {
      setError('Please select a research paper PDF or provide a GitHub repository URL.');
      return;
    }
    setError('');
    setLoading(true);

    try {
      const formData = new FormData();
      if (file) formData.append('file', file);
      if (repoUrl.trim()) formData.append('repo_url', repoUrl.trim());
      if (branch.trim()) formData.append('branch', branch.trim());

      const res = await api.ingest(formData);
      onIngested(res.experiment_id);
      onClose();
    } catch (err) {
      setError(err.message || 'Ingestion failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <UploadCloud size={20} color="var(--accent-blue)" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Ingest Research Experiment</h3>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {error && (
              <div style={{
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                padding: '0.75rem',
                borderRadius: '0.375rem',
                color: '#f87171',
                fontSize: '0.85rem',
                display: 'flex',
                gap: '0.5rem',
                alignItems: 'center',
              }}>
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.4rem', color: 'var(--text-muted)' }}>
                Research Paper (PDF)
              </label>
              <input
                type="file"
                accept=".pdf"
                className="input"
                style={{ width: '100%' }}
                onChange={(e) => setFile(e.target.files[0])}
              />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem', display: 'block' }}>
                Parsed using PyPDF2 / Docling with automated GitHub repo link and parameter extraction.
              </span>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.4rem', color: 'var(--text-muted)' }}>
                GitHub Repository URL (Optional if cited in PDF)
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <GitBranch size={18} color="var(--text-dim)" />
                <input
                  type="url"
                  placeholder="https://github.com/owner/repository"
                  className="input"
                  style={{ width: '100%' }}
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.4rem', color: 'var(--text-muted)' }}>
                Git Branch / Ref (Optional)
              </label>
              <input
                type="text"
                placeholder="main"
                className="input"
                style={{ width: '100%' }}
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 size={16} className="spin" />
                  <span>Ingesting & Extracting...</span>
                </>
              ) : (
                'Start Ingestion Pipeline'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

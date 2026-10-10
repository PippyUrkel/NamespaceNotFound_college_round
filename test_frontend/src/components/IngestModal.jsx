
import React, { useEffect, useRef, useState } from 'react';
import {
  X,
  UploadCloud,
  GitBranch,
  AlertCircle,
  Loader2,
  FileText,
  CheckCircle2,
  ArrowUpRight,
  Link2,
} from 'lucide-react';
import { api } from '../api';
import './IngestModal.css';

export default function IngestModal({ isOpen, onClose, onIngested }) {
  const [file, setFile] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !loading) onClose();
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, loading, onClose]);

  if (!isOpen) return null;

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0] || null;
    setFile(selectedFile);
    setError('');
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!file && !repoUrl.trim()) {
      setError(
        'Add a research paper PDF or provide a GitHub repository URL to continue.'
      );
      return;
    }

    if (file && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please choose a PDF file for the research paper.');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const formData = new FormData();

      if (file) formData.append('file', file);
      if (repoUrl.trim()) {
        formData.append('repo_url', repoUrl.trim());
      }
      if (branch.trim()) {
        formData.append('branch', branch.trim());
      }

      const response = await api.ingest(formData);

      onIngested(response.experiment_id);
      onClose();
    } catch (err) {
      setError(
        err?.message ||
          'Ingestion failed. Check the connection and try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget && !loading) {
      onClose();
    }
  }

  return (
    <div
      className="cg-ingest-overlay"
      onMouseDown={handleBackdropClick}
      role="presentation"
    >
      <section
        className="cg-ingest-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cg-ingest-title"
        aria-describedby="cg-ingest-description"
      >
        <header className="cg-ingest-header">
          <div className="cg-ingest-heading">
            <span className="cg-ingest-mark" aria-hidden="true">
              <UploadCloud size={19} strokeWidth={1.8} />
            </span>

            <div>
              <div className="cg-ingest-eyebrow">
                EXPERIMENT INTAKE / 01
              </div>

              <h2 id="cg-ingest-title">Ingest research</h2>

              <p id="cg-ingest-description">
                Build a reproducible experiment from a paper and its source
                repository.
              </p>
            </div>
          </div>

          <button
            type="button"
            className="cg-ingest-close"
            onClick={onClose}
            disabled={loading}
            aria-label="Close ingestion dialog"
          >
            <X size={18} />
          </button>
        </header>

        <form onSubmit={handleSubmit}>
          <div className="cg-ingest-body">
            <div className="cg-ingest-section-label">
              <span>INPUT SOURCES</span>
              <span className="cg-ingest-section-line" />
              <span className="cg-ingest-optional">
                PDF and repository optional individually
              </span>
            </div>

            {error && (
              <div className="cg-ingest-error" role="alert">
                <AlertCircle size={17} />
                <span>{error}</span>
              </div>
            )}

            <div className="cg-ingest-field">
              <div className="cg-ingest-label-row">
                <label htmlFor="cg-paper-file">Research paper</label>
                <span className="cg-ingest-tag">PDF</span>
              </div>

              <input
                ref={fileInputRef}
                id="cg-paper-file"
                type="file"
                accept=".pdf,application/pdf"
                className="cg-ingest-file-input"
                onChange={handleFileChange}
                disabled={loading}
              />

              <button
                type="button"
                className={`cg-ingest-dropzone${file ? ' has-file' : ''}`}
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
              >
                <span className="cg-ingest-file-icon">
                  {file ? (
                    <CheckCircle2 size={21} />
                  ) : (
                    <FileText size={21} />
                  )}
                </span>

                <span className="cg-ingest-drop-copy">
                  <strong>
                    {file ? file.name : 'Choose a paper to analyze'}
                  </strong>

                  <small>
                    {file
                      ? `${(file.size / (1024 * 1024)).toFixed(2)} MB · PDF selected`
                      : 'Select a PDF from your device'}
                  </small>
                </span>

                <span className="cg-ingest-browse">
                  {file ? 'Change' : 'Browse'}
                  <ArrowUpRight size={14} />
                </span>
              </button>

              <p className="cg-ingest-help">
                Paper parsing extracts cited repositories, experimental
                methods, and reported parameters.
              </p>
            </div>

            <div className="cg-ingest-divider">
              <span>AND / OR</span>
            </div>

            <div className="cg-ingest-field">
              <div className="cg-ingest-label-row">
                <label htmlFor="cg-repo-url">GitHub repository</label>
                <span className="cg-ingest-tag cg-ingest-tag-optional">
                  OPTIONAL
                </span>
              </div>

              <div className="cg-ingest-input-wrap">
                <GitBranch size={17} aria-hidden="true" />

                <input
                  id="cg-repo-url"
                  type="url"
                  placeholder="https://github.com/owner/repository"
                  value={repoUrl}
                  onChange={(event) => {
                    setRepoUrl(event.target.value);
                    setError('');
                  }}
                  disabled={loading}
                />

                <Link2
                  className="cg-ingest-input-end"
                  size={15}
                  aria-hidden="true"
                />
              </div>

              <p className="cg-ingest-help">
                Provide a repository directly, or let CrisisGrid look for one
                referenced in the paper.
              </p>
            </div>

            <div className="cg-ingest-field">
              <div className="cg-ingest-label-row">
                <label htmlFor="cg-repo-branch">Branch or ref</label>
                <span className="cg-ingest-tag cg-ingest-tag-optional">
                  OPTIONAL
                </span>
              </div>

              <div className="cg-ingest-input-wrap cg-ingest-branch-wrap">
                <GitBranch size={17} aria-hidden="true" />

                <input
                  id="cg-repo-branch"
                  type="text"
                  placeholder="main"
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  disabled={loading}
                />
              </div>

              <p className="cg-ingest-help">
                Leave blank to use the repository's default branch.
              </p>
            </div>

            <div className="cg-ingest-pipeline-note">
              <span className="cg-ingest-pulse" />

              <div>
                <strong>Pipeline preview</strong>
                <span>
                  Parse sources <i>→</i> extract claims <i>→</i> map experiment
                  configuration
                </span>
              </div>
            </div>
          </div>

          <footer className="cg-ingest-footer">
            <div className="cg-ingest-footer-note">
              <span className="cg-ingest-footer-dot" />
              <span>
                Sources are used to create a new experiment workspace.
              </span>
            </div>

            <div className="cg-ingest-actions">
              <button
                type="button"
                className="cg-ingest-cancel"
                onClick={onClose}
                disabled={loading}
              >
                Cancel
              </button>

              <button
                type="submit"
                className="cg-ingest-submit"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2
                      size={16}
                      className="cg-ingest-spinner"
                    />
                    <span>Processing sources…</span>
                  </>
                ) : (
                  <>
                    <UploadCloud size={16} />
                    <span>Start ingestion</span>
                    <ArrowUpRight size={14} />
                  </>
                )}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

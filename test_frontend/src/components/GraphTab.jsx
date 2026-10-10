import React, { useState } from 'react';
import { 
  GitFork, Sliders, History, Code2, Copy, Check, ArrowRight, 
  ExternalLink, Layers, Sparkles, CheckCircle2 
} from 'lucide-react';
import { api } from '../api';

export default function GraphTab({ 
  experimentId, 
  graph, 
  versions, 
  onVersionChange, 
  onRefreshGraph 
}) {
  const [selectedNodeId, setSelectedNodeId] = useState(
    graph?.nodes?.[0]?.id || 'setup_environment'
  );
  const [copiedCode, setCopiedCode] = useState(false);
  const [showTuneModal, setShowTuneModal] = useState(false);
  const [showDiffModal, setShowDiffModal] = useState(false);

  // Tune form state
  const [tuneParams, setTuneParams] = useState({
    learning_rate: graph?.parameters_summary?.learning_rate || '0.001',
    batch_size: graph?.parameters_summary?.batch_size || '64',
    epochs: graph?.parameters_summary?.epochs || '10',
    seed: graph?.parameters_summary?.seed || '42',
  });
  const [customNodeCode, setCustomNodeCode] = useState('');
  const [tuneTargetNode, setTuneTargetNode] = useState('');
  const [tuneDesc, setTuneDesc] = useState('');
  const [tuningLoading, setTuningLoading] = useState(false);

  // Diff state
  const [fromVer, setFromVer] = useState(versions?.[0]?.version_id || 'v1');
  const [toVer, setToVer] = useState(versions?.[versions.length - 1]?.version_id || 'v1');
  const [diffData, setDiffData] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);

  if (!graph || !graph.nodes) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No experiment graph generated yet.
      </div>
    );
  }

  const selectedNode = graph.nodes.find((n) => n.id === selectedNodeId) || graph.nodes[0];

  function copyCode() {
    if (selectedNode?.code) {
      navigator.clipboard.writeText(selectedNode.code);
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    }
  }

  async function handleTuneSubmit(e) {
    e.preventDefault();
    setTuningLoading(true);
    try {
      const payload = {
        parameters: {
          learning_rate: parseFloat(tuneParams.learning_rate) || tuneParams.learning_rate,
          batch_size: parseInt(tuneParams.batch_size, 10) || tuneParams.batch_size,
          epochs: parseInt(tuneParams.epochs, 10) || tuneParams.epochs,
          seed: parseInt(tuneParams.seed, 10) || tuneParams.seed,
        },
        change_description: tuneDesc || 'Parameter fine-tuning from studio',
      };
      if (tuneTargetNode && customNodeCode.trim()) {
        payload.node_id = tuneTargetNode;
        payload.code_updates = { [tuneTargetNode]: customNodeCode.trim() };
      }

      await api.tuneGraph(experimentId, payload);
      setShowTuneModal(false);
      onRefreshGraph();
    } catch (err) {
      alert('Tuning failed: ' + err.message);
    } finally {
      setTuningLoading(false);
    }
  }

  async function handleLoadDiff() {
    setDiffLoading(true);
    try {
      const data = await api.getGraphDiff(experimentId, fromVer, toVer);
      setDiffData(data);
    } catch (err) {
      alert('Diff failed: ' + err.message);
    } finally {
      setDiffLoading(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Bar with Version Switcher and Actions */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', padding: '0.85rem 1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Layers size={18} color="var(--accent-blue)" />
            <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Graph Version:</span>
          </div>
          <select 
            className="select" 
            value={graph.version_id} 
            onChange={(e) => onVersionChange(e.target.value)}
          >
            {(versions || []).map((v) => (
              <option key={v.version_id} value={v.version_id}>
                {v.version_id} {v.parent_version ? `(from ${v.parent_version})` : '(Initial synthesis)'}
              </option>
            ))}
          </select>

          <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
            Hash: {graph.graph_hash || 'computed'}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button 
            className="btn btn-secondary btn-sm" 
            onClick={() => {
              setShowDiffModal(true);
              handleLoadDiff();
            }}
          >
            <History size={14} /> Compare Versions (Diff)
          </button>
          <button 
            className="btn btn-primary btn-sm" 
            onClick={() => setShowTuneModal(true)}
          >
            <Sliders size={14} /> Tune Parameters & Create Version
          </button>
        </div>
      </div>

      {/* Main DAG Grid Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.8fr', gap: '1.25rem' }}>
        {/* DAG Pipeline Flow */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <GitFork size={16} color="var(--accent-cyan)" /> Experiment Execution DAG
            </h4>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{graph.nodes.length} isolated nodes</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {graph.nodes.map((node, index) => {
              const isSelected = node.id === selectedNodeId;
              const provSource = node.provenance?.source || 'deterministic_synthesis';

              return (
                <div 
                  key={node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                  style={{
                    background: isSelected ? 'rgba(59, 130, 246, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                    border: isSelected ? '1px solid var(--accent-blue)' : '1px solid var(--border)',
                    borderRadius: '0.5rem',
                    padding: '0.75rem 1rem',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{
                        width: '1.4rem',
                        height: '1.4rem',
                        borderRadius: '9999px',
                        background: 'rgba(255, 255, 255, 0.08)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        color: 'var(--text-muted)',
                      }}>
                        {index + 1}
                      </span>
                      <strong style={{ fontSize: '0.875rem', color: isSelected ? '#93c5fd' : '#f1f5f9' }}>
                        {node.name}
                      </strong>
                    </div>

                    <span className={`badge ${
                      provSource === 'tuned' ? 'badge-purple' :
                      provSource === 'repository' ? 'badge-blue' :
                      provSource === 'assumed' ? 'badge-amber' : 'badge-green'
                    }`}>
                      {provSource}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.775rem', color: 'var(--text-muted)', marginBottom: '0.5rem', lineHeight: 1.4 }}>
                    {node.description}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.725rem', color: 'var(--text-dim)' }}>
                    <span>Type: <code style={{ color: 'var(--accent-cyan)' }}>{node.type}</code></span>
                    {node.upstream.length > 0 && (
                      <span>Depends on: {node.upstream.length} upstream</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Node Details & Code Block */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>{selectedNode.name}</h3>
                <span className="badge badge-blue">{selectedNode.type}</span>
              </div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{selectedNode.id}</code>
              </p>
            </div>

            <button className="btn btn-secondary btn-sm" onClick={copyCode}>
              {copiedCode ? <Check size={14} color="#34d399" /> : <Copy size={14} />}
              <span>{copiedCode ? 'Copied' : 'Copy Code'}</span>
            </button>
          </div>

          {/* Node Parameters */}
          {selectedNode.parameters && Object.keys(selectedNode.parameters).length > 0 && (
            <div style={{
              background: 'rgba(0, 0, 0, 0.25)',
              border: '1px solid var(--border)',
              borderRadius: '0.5rem',
              padding: '0.75rem',
            }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
                Node Bound Parameters
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {Object.entries(selectedNode.parameters).map(([pk, pv]) => (
                  <div key={pk} style={{
                    background: 'rgba(255, 255, 255, 0.05)',
                    padding: '0.25rem 0.5rem',
                    borderRadius: '0.25rem',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                  }}>
                    <span style={{ color: 'var(--text-muted)' }}>{pk}:</span>{' '}
                    <span style={{ color: 'var(--accent-cyan)' }}>{String(pv)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Executable Python Code */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Isolated Container Code Block
              </span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                Config Hash: {selectedNode.config_hash || 'auto'}
              </span>
            </div>
            <pre className="code-block" style={{ maxHeight: '380px', flex: 1 }}>
              {selectedNode.code}
            </pre>
          </div>
        </div>
      </div>

      {/* Parameter Fine-Tuning Modal */}
      {showTuneModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sliders size={18} color="var(--accent-blue)" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Fine-Tune Parameters & Version Graph</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowTuneModal(false)}>✕</button>
            </div>

            <form onSubmit={handleTuneSubmit}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Modifying hyperparameters or code generates an <strong>immutable new graph version</strong> with full provenance and diff tracking.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                      Learning Rate
                    </label>
                    <input
                      type="text"
                      className="input"
                      style={{ width: '100%' }}
                      value={tuneParams.learning_rate}
                      onChange={(e) => setTuneParams({ ...tuneParams, learning_rate: e.target.value })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                      Batch Size
                    </label>
                    <input
                      type="text"
                      className="input"
                      style={{ width: '100%' }}
                      value={tuneParams.batch_size}
                      onChange={(e) => setTuneParams({ ...tuneParams, batch_size: e.target.value })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                      Training Epochs
                    </label>
                    <input
                      type="text"
                      className="input"
                      style={{ width: '100%' }}
                      value={tuneParams.epochs}
                      onChange={(e) => setTuneParams({ ...tuneParams, epochs: e.target.value })}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                      Base Seed
                    </label>
                    <input
                      type="text"
                      className="input"
                      style={{ width: '100%' }}
                      value={tuneParams.seed}
                      onChange={(e) => setTuneParams({ ...tuneParams, seed: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Target Specific Node for Custom Code (Optional)
                  </label>
                  <select 
                    className="select" 
                    style={{ width: '100%' }}
                    value={tuneTargetNode}
                    onChange={(e) => setTuneTargetNode(e.target.value)}
                  >
                    <option value="">No node custom code</option>
                    {graph.nodes.map((n) => (
                      <option key={n.id} value={n.id}>{n.name} ({n.id})</option>
                    ))}
                  </select>
                </div>

                {tuneTargetNode && (
                  <div>
                    <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                      Custom Replacement Code for {tuneTargetNode}
                    </label>
                    <textarea
                      rows={5}
                      className="input"
                      style={{ width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}
                      value={customNodeCode}
                      onChange={(e) => setCustomNodeCode(e.target.value)}
                      placeholder="# Custom code to execute in this node container..."
                    />
                  </div>
                )}

                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                    Change Description / Reason
                  </label>
                  <input
                    type="text"
                    className="input"
                    style={{ width: '100%' }}
                    placeholder="e.g. Doubled batch size and lowered learning rate for stability"
                    value={tuneDesc}
                    onChange={(e) => setTuneDesc(e.target.value)}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowTuneModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={tuningLoading}>
                  {tuningLoading ? 'Creating Version...' : 'Create New Immutable Version'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Graph Diff Modal */}
      {showDiffModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '850px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <History size={18} color="var(--accent-indigo)" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Graph Version Diff</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowDiffModal(false)}>✕</button>
            </div>

            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>From Version: </span>
                  <select className="select" value={fromVer} onChange={(e) => setFromVer(e.target.value)}>
                    {(versions || []).map((v) => (
                      <option key={v.version_id} value={v.version_id}>{v.version_id}</option>
                    ))}
                  </select>
                </div>
                <ArrowRight size={16} color="var(--text-dim)" />
                <div>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>To Version: </span>
                  <select className="select" value={toVer} onChange={(e) => setToVer(e.target.value)}>
                    {(versions || []).map((v) => (
                      <option key={v.version_id} value={v.version_id}>{v.version_id}</option>
                    ))}
                  </select>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={handleLoadDiff} disabled={diffLoading}>
                  {diffLoading ? 'Comparing...' : 'Compare'}
                </button>
              </div>

              {diffData && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {/* Parameter Changes */}
                  <div className="card" style={{ padding: '0.85rem' }}>
                    <h5 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>Parameter Modifications</h5>
                    {Object.keys(diffData.parameter_changes || {}).length > 0 ? (
                      <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                            <th style={{ padding: '0.4rem' }}>Parameter</th>
                            <th style={{ padding: '0.4rem' }}>{diffData.from_version} (Old)</th>
                            <th style={{ padding: '0.4rem' }}>{diffData.to_version} (New)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(diffData.parameter_changes).map(([k, ch]) => (
                            <tr key={k} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                              <td style={{ padding: '0.4rem', fontWeight: 600 }}>{k}</td>
                              <td style={{ padding: '0.4rem', color: '#f87171', fontFamily: 'var(--font-mono)' }}>{String(ch.old)}</td>
                              <td style={{ padding: '0.4rem', color: '#34d399', fontFamily: 'var(--font-mono)' }}>{String(ch.new)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>No parameter differences.</span>
                    )}
                  </div>

                  {/* Code Diffs */}
                  {Object.keys(diffData.code_changes || {}).length > 0 && (
                    <div className="card" style={{ padding: '0.85rem' }}>
                      <h5 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>Code Modifications</h5>
                      {Object.entries(diffData.code_changes).map(([nodeId, diffObj]) => (
                        <div key={nodeId} style={{ marginBottom: '0.75rem' }}>
                          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--accent-blue)' }}>Node: {nodeId}</span>
                          <pre className="code-block" style={{ maxHeight: '200px', fontSize: '0.75rem' }}>
                            {diffObj.unified_diff || 'No code changes'}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowDiffModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

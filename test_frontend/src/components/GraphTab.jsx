import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  Panel,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  GitFork,
  SlidersHorizontal,
  History,
  Copy,
  Check,
  ArrowRight,
  Layers3,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Wrench,
  ShieldCheck,
  RefreshCw,
  Code2,
  Hash,
  GitBranch,
  X,
  FileCode2,
  CircleHelp,
  ChevronRight,
  ChevronDown,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  Database,
  Box,
  Braces,
  Clock3,
} from 'lucide-react';
import { api } from '../api';
import './GraphTab.css';

const PROVENANCE = {
  repository: { label: 'Repository', tone: 'repository' },
  assumed: { label: 'Assumed', tone: 'assumed' },
  tuned: { label: 'Tuned', tone: 'tuned' },
  deterministic_synthesis: { label: 'Synthesized', tone: 'synthesized' },
};

const TYPE_ICONS = {
  setup: Layers3,
  environment: Layers3,
  data: Database,
  dataset: Database,
  load: Database,
  train: Code2,
  model: Box,
  evaluate: CheckCircle2,
  metric: CheckCircle2,
  save: FileCode2,
  artifact: FileCode2,
};

function provenanceFor(node) {
  const source = node?.provenance?.source || 'deterministic_synthesis';
  return PROVENANCE[source] || {
    label: String(source).replaceAll('_', ' '),
    tone: 'synthesized',
  };
}

function nodeIcon(node) {
  const hint = `${node?.type || ''} ${node?.name || ''} ${node?.id || ''}`.toLowerCase();
  const key = Object.keys(TYPE_ICONS).find((candidate) => hint.includes(candidate));
  return key ? TYPE_ICONS[key] : Braces;
}

function getNodeParameters(node) {
  if (node?.parameters && typeof node.parameters === 'object' && !Array.isArray(node.parameters)) {
    return node.parameters;
  }
  return {};
}

function buildFlowLayout(rawNodes) {
  const nodes = Array.isArray(rawNodes) ? rawNodes : [];
  const ids = new Set(nodes.map((node) => String(node.id)));
  const parents = new Map();
  const children = new Map(nodes.map((node) => [String(node.id), []]));

  nodes.forEach((node) => {
    const id = String(node.id);
    const upstream = Array.isArray(node.upstream)
      ? node.upstream.map((item) => typeof item === 'string' ? item : item?.id).filter(Boolean).map(String)
      : [];
    const validParents = upstream.filter((parentId) => ids.has(parentId) && parentId !== id);
    parents.set(id, validParents);
    validParents.forEach((parentId) => children.get(parentId)?.push(id));
  });

  // Some graph payloads contain ordered nodes but no explicit upstream references.
  // In that case, create a readable sequential pipeline rather than a disconnected canvas.
  const hasExplicitRelationships = [...parents.values()].some((items) => items.length > 0);
  if (!hasExplicitRelationships && nodes.length > 1) {
    nodes.forEach((node, index) => {
      const id = String(node.id);
      if (index > 0) parents.set(id, [String(nodes[index - 1].id)]);
      if (index < nodes.length - 1) children.get(id)?.push(String(nodes[index + 1].id));
    });
  }

  // Assign a layer using the longest parent path. Cycles are bounded and surfaced
  // without allowing layout to loop forever.
  const layerById = new Map();
  const visiting = new Set();
  const getLayer = (id, depth = 0) => {
    if (layerById.has(id)) return layerById.get(id);
    if (visiting.has(id) || depth > nodes.length + 2) return 0;
    visiting.add(id);
    const upstream = parents.get(id) || [];
    const layer = upstream.length ? Math.max(...upstream.map((parentId) => getLayer(parentId, depth + 1))) + 1 : 0;
    visiting.delete(id);
    layerById.set(id, layer);
    return layer;
  };
  nodes.forEach((node) => getLayer(String(node.id)));

  const byLayer = new Map();
  nodes.forEach((node) => {
    const layer = layerById.get(String(node.id)) || 0;
    if (!byLayer.has(layer)) byLayer.set(layer, []);
    byLayer.get(layer).push(node);
  });

  const positions = new Map();
  [...byLayer.entries()].sort((a, b) => a[0] - b[0]).forEach(([layer, layerNodes]) => {
    layerNodes.forEach((node, index) => {
      positions.set(String(node.id), { x: 70 + layer * 300, y: 70 + index * 155 });
    });
  });

  const flowNodes = nodes.map((node, index) => ({
    id: String(node.id),
    type: 'experimentNode',
    position: positions.get(String(node.id)) || { x: 70, y: 70 + index * 155 },
    data: { node, order: index + 1 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }));

  const edges = [];
  parents.forEach((upstreamIds, targetId) => {
    upstreamIds.forEach((sourceId) => {
      edges.push({
        id: `${sourceId}__${targetId}`,
        source: sourceId,
        target: targetId,
        type: 'smoothstep',
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#718486' },
        style: { stroke: '#526467', strokeWidth: 1.5 },
      });
    });
  });

  return { nodes: flowNodes, edges };
}

function ExperimentFlowNode({ data, selected }) {
  const node = data.node;
  const provenance = provenanceFor(node);
  const Icon = nodeIcon(node);
  const parameters = getNodeParameters(node);
  const parameterCount = Object.keys(parameters).length;
  const codeLines = typeof node.code === 'string' && node.code.length
    ? node.code.split('\n').length
    : 0;

  return (
    <article className={`cg-flow-node ${selected ? 'is-selected' : ''} cg-flow-node--${provenance.tone}`}>
      <Handle type="target" position={Position.Left} className="cg-flow-handle" />
      <div className="cg-flow-node__topline">
        <span className="cg-flow-node__ordinal">{String(data.order).padStart(2, '0')}</span>
        <span className={`cg-flow-node__icon cg-flow-node__icon--${provenance.tone}`}><Icon size={15} /></span>
        <span className={`cg-flow-provenance cg-flow-provenance--${provenance.tone}`}>{provenance.label}</span>
      </div>
      <div className="cg-flow-node__title" title={node.name || node.id}>{node.name || node.id}</div>
      <div className="cg-flow-node__id" title={node.id}>{node.id}</div>
      <p className="cg-flow-node__description">{node.description || 'No node description provided.'}</p>
      <div className="cg-flow-node__footer">
        <span><Braces size={11} /> {node.type || 'process'}</span>
        <span><SlidersHorizontal size={11} /> {parameterCount} params</span>
        {codeLines > 0 && <span><Code2 size={11} /> {codeLines} lines</span>}
      </div>
      <Handle type="source" position={Position.Right} className="cg-flow-handle" />
    </article>
  );
}

const nodeTypes = { experimentNode: memo(ExperimentFlowNode) };

function Modal({ title, eyebrow, icon: Icon, onClose, className = '', children, footer }) {
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="graph-modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className={`graph-modal ${className}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="graph-modal__header">
          <div className="graph-modal__title-wrap">
            <span className="graph-modal__icon"><Icon size={18} /></span>
            <div>
              {eyebrow && <p className="graph-eyebrow">{eyebrow}</p>}
              <h3>{title}</h3>
            </div>
          </div>
          <button className="graph-icon-button" type="button" onClick={onClose} aria-label="Close dialog"><X size={17} /></button>
        </header>
        <div className="graph-modal__body">{children}</div>
        {footer && <footer className="graph-modal__footer">{footer}</footer>}
      </section>
    </div>
  );
}

function InspectorSection({ title, count, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="cg-inspector-section">
      <button className="cg-inspector-section__toggle" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span>{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{title}</span>
        {count !== undefined && <span className="cg-inspector-section__count">{count}</span>}
      </button>
      {open && <div className="cg-inspector-section__content">{children}</div>}
    </section>
  );
}

function Inspector({ node, onClose, onCopyCode, copiedCode }) {
  if (!node) return (
    <aside className="cg-node-inspector cg-node-inspector--empty">
      <div className="cg-inspector-empty-icon"><CircleHelp size={21} /></div>
      <h3>Select a node</h3>
      <p>Click any node on the canvas to inspect its configuration, parameters, code, and provenance.</p>
    </aside>
  );

  const provenance = provenanceFor(node);
  const parameters = getNodeParameters(node);
  const inputs = node.inputs && typeof node.inputs === 'object' ? node.inputs : {};
  const outputs = node.outputs && typeof node.outputs === 'object' ? node.outputs : {};
  const metadata = node.metadata && typeof node.metadata === 'object' ? node.metadata : {};
  const code = node.code || '';

  return (
    <aside className="cg-node-inspector">
      <header className="cg-node-inspector__header">
        <div>
          <p className="graph-eyebrow">NODE INSPECTOR / SELECTED</p>
          <h3>{node.name || node.id}</h3>
        </div>
        <button className="graph-icon-button" type="button" onClick={onClose} aria-label="Close node inspector"><PanelRightClose size={16} /></button>
      </header>

      <div className="cg-inspector-identity">
        <span className="cg-inspector-node-mark"><Code2 size={16} /></span>
        <div className="cg-inspector-identity__text">
          <span className="cg-inspector-label">NODE ID</span>
          <code>{node.id}</code>
        </div>
        <span className={`graph-provenance graph-provenance--${provenance.tone}`}>{provenance.label}</span>
      </div>

      {node.description && <p className="cg-inspector-description">{node.description}</p>}

      <InspectorSection title="Configuration" count={Object.keys(metadata).length + 1}>
        <div className="cg-inspector-kv"><span>Type</span><code>{node.type || 'unknown'}</code></div>
        <div className="cg-inspector-kv"><span>Config hash</span><code>{node.config_hash || 'Not provided'}</code></div>
        {Object.entries(metadata).map(([key, value]) => (
          <div className="cg-inspector-kv" key={key}><span>{key.replaceAll('_', ' ')}</span><code>{formatValue(value)}</code></div>
        ))}
      </InspectorSection>

      <InspectorSection title="Parameters" count={Object.keys(parameters).length}>
        {Object.keys(parameters).length ? Object.entries(parameters).map(([key, value]) => (
          <div className="cg-inspector-parameter" key={key}>
            <span>{key}</span><code>{formatValue(value)}</code>
          </div>
        )) : <p className="cg-inspector-empty-copy">No explicit parameters recorded for this node.</p>}
      </InspectorSection>

      {(Object.keys(inputs).length > 0 || Object.keys(outputs).length > 0) && (
        <InspectorSection title="Inputs & outputs" count={Object.keys(inputs).length + Object.keys(outputs).length}>
          {Object.keys(inputs).length > 0 && <div className="cg-inspector-io"><span className="cg-inspector-label">INPUTS</span>{Object.entries(inputs).map(([key, value]) => <div className="cg-inspector-kv" key={`in-${key}`}><span>{key}</span><code>{formatValue(value)}</code></div>)}</div>}
          {Object.keys(outputs).length > 0 && <div className="cg-inspector-io"><span className="cg-inspector-label">OUTPUTS</span>{Object.entries(outputs).map(([key, value]) => <div className="cg-inspector-kv" key={`out-${key}`}><span>{key}</span><code>{formatValue(value)}</code></div>)}</div>}
        </InspectorSection>
      )}

      <InspectorSection title="Provenance" count={node.provenance ? Object.keys(node.provenance).length : 1}>
        {node.provenance && typeof node.provenance === 'object' ? Object.entries(node.provenance).map(([key, value]) => (
          <div className="cg-inspector-kv" key={key}><span>{key.replaceAll('_', ' ')}</span><code>{formatValue(value)}</code></div>
        )) : <div className="cg-inspector-kv"><span>Source</span><code>{provenance.label}</code></div>}
      </InspectorSection>

      <InspectorSection title="Source code" count={code ? `${code.split('\n').length} lines` : 'Unavailable'} defaultOpen>
        <div className="cg-inspector-code-heading">
          <span><FileCode2 size={13} /> PYTHON SOURCE</span>
          <button className="graph-button graph-button--quiet" type="button" onClick={() => onCopyCode(code)} disabled={!code}>
            {copiedCode ? <Check size={13} /> : <Copy size={13} />}{copiedCode ? 'Copied' : 'Copy'}
          </button>
        </div>
        <pre className="cg-inspector-code"><code>{code || '# No code was included in the graph payload.'}</code></pre>
      </InspectorSection>
    </aside>
  );
}

function formatValue(value) {
  if (value === null) return 'null';
  if (value === undefined) return '—';
  if (typeof value === 'object') {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return String(value);
}

export default function GraphTab({ experimentId, graph, versions, onVersionChange, onRefreshGraph }) {
  const rawNodes = graph?.nodes || [];
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [copiedCode, setCopiedCode] = useState(false);
  const [showTuneModal, setShowTuneModal] = useState(false);
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [validationReport, setValidationReport] = useState(null);
  const [validating, setValidating] = useState(false);
  const [remediating, setRemediating] = useState(false);
  const [showIssuesList, setShowIssuesList] = useState(true);
  const [tuneParams, setTuneParams] = useState({
    learning_rate: String(graph?.parameters_summary?.learning_rate ?? '0.001'),
    batch_size: String(graph?.parameters_summary?.batch_size ?? '64'),
    epochs: String(graph?.parameters_summary?.epochs ?? '10'),
    seed: String(graph?.parameters_summary?.seed ?? '42'),
  });
  const [customNodeCode, setCustomNodeCode] = useState('');
  const [tuneTargetNode, setTuneTargetNode] = useState('');
  const [tuneDesc, setTuneDesc] = useState('');
  const [tuningLoading, setTuningLoading] = useState(false);
  const [fromVer, setFromVer] = useState(versions?.[0]?.version_id || graph?.version_id || 'v1');
  const [toVer, setToVer] = useState(versions?.[versions.length - 1]?.version_id || graph?.version_id || 'v1');
  const [diffData, setDiffData] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const { nodes: initialFlowNodes, edges: initialEdges } = useMemo(() => buildFlowLayout(rawNodes), [rawNodes, graph?.version_id]);
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(initialFlowNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setFlowNodes(initialFlowNodes);
    setFlowEdges(initialEdges);
    setSelectedNodeId((current) => rawNodes.some((node) => String(node.id) === current) ? current : String(rawNodes[0]?.id || ''));
  }, [initialFlowNodes, initialEdges, rawNodes, setFlowNodes, setFlowEdges]);

  useEffect(() => {
    setTuneParams({
      learning_rate: String(graph?.parameters_summary?.learning_rate ?? '0.001'),
      batch_size: String(graph?.parameters_summary?.batch_size ?? '64'),
      epochs: String(graph?.parameters_summary?.epochs ?? '10'),
      seed: String(graph?.parameters_summary?.seed ?? '42'),
    });
  }, [graph?.version_id]);

  useEffect(() => {
    if (experimentId && graph?.version_id) handleValidate(graph.version_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experimentId, graph?.version_id]);

  useEffect(() => {
    if (versions?.length) {
      setFromVer((current) => versions.some((version) => version.version_id === current) ? current : versions[0].version_id);
      setToVer((current) => versions.some((version) => version.version_id === current) ? current : versions[versions.length - 1].version_id);
    }
  }, [versions]);

  const selectedNode = rawNodes.find((node) => String(node.id) === selectedNodeId) || null;

  const handleNodeClick = useCallback((_, flowNode) => {
    setSelectedNodeId(flowNode.id);
    setInspectorOpen(true);
  }, []);

  const handleValidate = async (versionId = null) => {
    if (!experimentId) return;
    setValidating(true);
    try {
      const report = await api.validateGraph(experimentId, versionId || graph?.version_id);
      setValidationReport(report);
    } catch (error) {
      console.error('Graph validation failed:', error);
      setValidationReport({ is_valid: false, total_errors: 1, total_warnings: 0, issues: [{ node_id: 'graph', severity: 'error', category: 'request_failed', message: error.message || 'Validation request failed.' }] });
    } finally {
      setValidating(false);
    }
  };

  const handleRemediate = async () => {
    if (!experimentId) return;
    setRemediating(true);
    try {
      const result = await api.remediateGraph(experimentId, graph?.version_id);
      if (result.remediated) {
        onRefreshGraph?.();
        if (result.version?.version_id) onVersionChange?.(result.version.version_id);
        setValidationReport(result.report);
      } else {
        window.alert('No auto-remediations required for this graph version.');
      }
    } catch (error) {
      window.alert(`Remediation failed: ${error.message}`);
    } finally {
      setRemediating(false);
    }
  };

  const copyCode = async (code) => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(true);
      window.setTimeout(() => setCopiedCode(false), 1800);
    } catch (error) {
      console.error('Unable to copy node code:', error);
    }
  };

  const handleTuneSubmit = async (event) => {
    event.preventDefault();
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
      onRefreshGraph?.();
    } catch (error) {
      window.alert(`Tuning failed: ${error.message}`);
    } finally {
      setTuningLoading(false);
    }
  };

  const handleLoadDiff = async () => {
    if (!experimentId || !fromVer || !toVer) return;
    setDiffLoading(true);
    setDiffData(null);
    try {
      const data = await api.getGraphDiff(experimentId, fromVer, toVer);
      setDiffData(data);
    } catch (error) {
      window.alert(`Diff failed: ${error.message}`);
    } finally {
      setDiffLoading(false);
    }
  };

  const onPaneClick = useCallback(() => setSelectedNodeId(''), []);

  if (!graph || !Array.isArray(graph.nodes)) {
    return (
      <section className="graph-empty">
        <span className="graph-empty__icon"><GitFork size={22} /></span>
        <p className="graph-eyebrow">EXPERIMENT GRAPH / WAITING</p>
        <h3>No execution graph yet</h3>
        <p>Generate an experiment graph to inspect node dependencies, synthesized code, provenance, and validation results.</p>
      </section>
    );
  }

  return (
    <div className="graph-workspace">
      <header className="graph-page-heading">
        <div>
          <p className="graph-eyebrow">EXPERIMENT STRUCTURE / 02</p>
          <h2>Experiment graph</h2>
          <p>Explore the full execution pipeline. Select a node to inspect its configuration, code, and provenance.</p>
        </div>
        <div className="graph-page-stat"><GitFork size={15} /><strong>{rawNodes.length}</strong><span>nodes · DAG canvas</span></div>
      </header>

      <section className="graph-toolbar">
        <div className="graph-version-control">
          <span className="graph-toolbar__icon"><Layers3 size={17} /></span>
          <div className="graph-version-control__label">
            <span>Graph version</span>
            <select value={graph.version_id || ''} onChange={(event) => onVersionChange?.(event.target.value)} aria-label="Graph version">
              {(versions || []).map((version) => (
                <option key={version.version_id} value={version.version_id}>
                  {version.version_id} {version.parent_version ? `(from ${version.parent_version})` : '(Initial synthesis)'}
                </option>
              ))}
              {!versions?.length && graph.version_id && <option value={graph.version_id}>{graph.version_id}</option>}
            </select>
          </div>
          <div className="graph-hash"><Hash size={12} /><span>{graph.graph_hash || 'hash pending'}</span></div>
        </div>
        <div className="graph-toolbar__actions">
          <button className="graph-button graph-button--quiet" type="button" onClick={() => handleValidate()} disabled={validating}>
            <RefreshCw size={14} className={validating ? 'graph-spin' : ''} />{validating ? 'Validating…' : 'Validate code'}
          </button>
          <button className="graph-button graph-button--quiet" type="button" onClick={() => { setShowDiffModal(true); setDiffData(null); }}><History size={14} />Compare versions</button>
          <button className="graph-button graph-button--primary" type="button" onClick={() => setShowTuneModal(true)}><SlidersHorizontal size={14} />Tune parameters</button>
        </div>
      </section>

      {validationReport && (
        <section className={`graph-validation ${validationReport.is_valid ? 'graph-validation--valid' : 'graph-validation--invalid'}`}>
          <div className="graph-validation__top">
            <div className="graph-validation__status">
              <span className="graph-validation__icon">{validationReport.is_valid ? <ShieldCheck size={19} /> : <AlertTriangle size={19} />}</span>
              <div><p className="graph-eyebrow">STATIC ANALYSIS / SEQUENTIAL SYMBOL FLOW</p><h3>{validationReport.is_valid ? 'Code flow verified' : 'Validation needs attention'}</h3></div>
              <span className={`graph-status-pill ${validationReport.is_valid ? 'graph-status-pill--success' : 'graph-status-pill--danger'}`}>{validationReport.is_valid ? 'PASSED' : 'ACTION REQUIRED'}</span>
            </div>
            <div className="graph-validation__actions">
              {!validationReport.is_valid && validationReport.can_auto_remediate && <button className="graph-button graph-button--warning" type="button" onClick={handleRemediate} disabled={remediating}><Wrench size={14} />{remediating ? 'Applying fixes…' : 'Auto-remediate'}</button>}
              <button className="graph-button graph-button--quiet" type="button" onClick={() => setShowIssuesList((current) => !current)}>{showIssuesList ? 'Hide details' : 'Show details'}</button>
            </div>
          </div>
          {!validationReport.is_valid && <div className="graph-validation__counts"><span><XCircle size={13} />{validationReport.total_errors ?? 0} errors</span><span><AlertTriangle size={13} />{validationReport.total_warnings ?? 0} warnings</span></div>}
          {!validationReport.is_valid && showIssuesList && validationReport.issues?.length > 0 && (
            <div className="graph-issues">
              <p className="graph-issues__intro">Potential sequential runtime failures reported by the validator.</p>
              {validationReport.issues.map((issue, index) => (
                <article className={`graph-issue graph-issue--${issue.severity === 'error' ? 'error' : 'warning'}`} key={`${issue.node_id}-${issue.line_number}-${index}`}>
                  <div className="graph-issue__top">
                    <div className="graph-issue__location"><span>NODE</span><code>{issue.node_id}</code>{issue.line_number && <span className="graph-issue__line">LINE {issue.line_number}</span>}</div>
                    <div className="graph-issue__tags"><span className={`graph-mini-tag graph-mini-tag--${issue.severity === 'error' ? 'danger' : 'warning'}`}>{issue.category}</span>{issue.symbol && <span className="graph-mini-tag graph-mini-tag--symbol">{issue.symbol}</span>}</div>
                  </div>
                  <p>{issue.message}</p>
                  {issue.suggested_fix && <div className="graph-issue__fix"><strong>Suggested fix</strong><code>{issue.suggested_fix}</code></div>}
                </article>
              ))}
            </div>
          )}
          {validationReport.is_valid && <p className="graph-validation__success-copy"><CheckCircle2 size={14} />No sequential code-flow issues were reported for this graph version.</p>}
        </section>
      )}

      <section className={`cg-graph-shell ${inspectorOpen ? '' : 'cg-graph-shell--inspector-closed'}`}>
        <div className="cg-canvas-panel">
          <div className="cg-canvas-topbar">
            <div className="cg-canvas-heading">
              <span className="graph-panel__icon graph-panel__icon--cyan"><GitFork size={16} /></span>
              <div><p className="graph-eyebrow">PIPELINE / DIRECTED ACYCLIC GRAPH</p><h3>Execution canvas</h3></div>
            </div>
            <div className="cg-canvas-actions">
              <span className="cg-canvas-hint">Drag to pan · Scroll to zoom · Click a node to inspect</span>
              <button className="graph-icon-button" type="button" onClick={() => setInspectorOpen((open) => !open)} aria-label={inspectorOpen ? 'Hide node inspector' : 'Show node inspector'} title={inspectorOpen ? 'Hide node inspector' : 'Show node inspector'}>
                {inspectorOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
              </button>
            </div>
          </div>
          <div className="cg-flow-canvas">
            {rawNodes.length ? (
              <ReactFlow
                nodes={flowNodes.map((node) => ({ ...node, selected: node.id === selectedNodeId }))}
                edges={flowEdges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={handleNodeClick}
                onPaneClick={onPaneClick}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2, minZoom: 0.25, maxZoom: 1 }}
                minZoom={0.15}
                maxZoom={1.6}
                nodesDraggable
                nodesConnectable={false}
                elementsSelectable
                proOptions={{ hideAttribution: true }}
                defaultEdgeOptions={{ type: 'smoothstep' }}
              >
                <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#293638" />
                <Controls showInteractive={false} />
                <MiniMap
                  pannable
                  zoomable
                  nodeColor={(node) => {
                    const tone = node.data?.node ? provenanceFor(node.data.node).tone : 'synthesized';
                    return ({ repository: '#B6A0FF', assumed: '#FFB86B', tuned: '#65DFF2', synthesized: '#61E6A6' })[tone] || '#61E6A6';
                  }}
                  maskColor="rgba(7, 11, 12, 0.78)"
                />
                <Panel position="top-right" className="cg-canvas-count">
                  <span className="cg-canvas-count__dot" />{rawNodes.length} NODES <span>/</span> {flowEdges.length} EDGES
                </Panel>
              </ReactFlow>
            ) : (
              <div className="cg-canvas-empty"><GitFork size={25} /><strong>This graph has no nodes</strong><span>The selected graph version did not return any pipeline nodes.</span></div>
            )}
          </div>
          <footer className="cg-canvas-legend">
            <span><i className="cg-legend-swatch cg-legend-swatch--repository" />Repository</span>
            <span><i className="cg-legend-swatch cg-legend-swatch--assumed" />Assumed</span>
            <span><i className="cg-legend-swatch cg-legend-swatch--tuned" />Tuned</span>
            <span><i className="cg-legend-swatch cg-legend-swatch--synthesized" />Synthesized</span>
            <span className="cg-legend-spacer" />
            <span className="cg-legend-note"><Clock3 size={12} /> Graph version: {graph.version_id || '—'}</span>
          </footer>
        </div>

        {inspectorOpen && (
          <Inspector
            node={selectedNode}
            onClose={() => setInspectorOpen(false)}
            onCopyCode={copyCode}
            copiedCode={copiedCode}
          />
        )}
      </section>

      {showTuneModal && (
        <Modal
          title="Tune parameters"
          eyebrow="CREATE GRAPH VERSION"
          icon={SlidersHorizontal}
          onClose={() => setShowTuneModal(false)}
          className="graph-tune-modal"
          footer={<><button className="graph-button graph-button--quiet" type="button" onClick={() => setShowTuneModal(false)}>Cancel</button><button className="graph-button graph-button--primary" type="submit" form="graph-tune-form" disabled={tuningLoading}>{tuningLoading ? 'Creating version…' : 'Create immutable version'}</button></>}
        >
          <p className="graph-modal__description">Changing hyperparameters or node code creates a new immutable graph version with provenance and diff tracking.</p>
          <form id="graph-tune-form" onSubmit={handleTuneSubmit} className="graph-form">
            <div className="graph-form__grid">
              {[['learning_rate', 'Learning rate'], ['batch_size', 'Batch size'], ['epochs', 'Training epochs'], ['seed', 'Base seed']].map(([key, label]) => (
                <label className="graph-field" key={key}><span>{label}</span><input value={tuneParams[key]} onChange={(event) => setTuneParams((current) => ({ ...current, [key]: event.target.value }))} /></label>
              ))}
            </div>
            <label className="graph-field"><span>Target node <em>OPTIONAL</em></span><select value={tuneTargetNode} onChange={(event) => setTuneTargetNode(event.target.value)}><option value="">No node-specific code</option>{rawNodes.map((node) => <option key={node.id} value={node.id}>{node.name || node.id} ({node.id})</option>)}</select></label>
            {tuneTargetNode && <label className="graph-field"><span>Replacement code for {tuneTargetNode}</span><textarea rows={7} value={customNodeCode} onChange={(event) => setCustomNodeCode(event.target.value)} placeholder="# Custom code to execute in this node container…" /></label>}
            <label className="graph-field"><span>Change description</span><input value={tuneDesc} onChange={(event) => setTuneDesc(event.target.value)} placeholder="e.g. Lowered learning rate for stability" /></label>
          </form>
        </Modal>
      )}

      {showDiffModal && (
        <Modal
          title="Graph version diff"
          eyebrow="PROVENANCE / COMPARISON"
          icon={History}
          onClose={() => setShowDiffModal(false)}
          className="graph-diff-modal"
          footer={<button className="graph-button graph-button--quiet" type="button" onClick={() => setShowDiffModal(false)}>Close</button>}
        >
          <div className="graph-diff-controls">
            <label className="graph-field"><span>From version</span><select value={fromVer} onChange={(event) => setFromVer(event.target.value)}>{(versions || []).map((version) => <option key={version.version_id} value={version.version_id}>{version.version_id}</option>)}</select></label>
            <ArrowRight size={16} className="graph-diff-arrow" />
            <label className="graph-field"><span>To version</span><select value={toVer} onChange={(event) => setToVer(event.target.value)}>{(versions || []).map((version) => <option key={version.version_id} value={version.version_id}>{version.version_id}</option>)}</select></label>
            <button className="graph-button graph-button--primary" type="button" onClick={handleLoadDiff} disabled={diffLoading}>{diffLoading ? 'Comparing…' : 'Compare'}</button>
          </div>
          {diffLoading && <div className="graph-diff-state"><RefreshCw size={16} className="graph-spin" />Loading version differences…</div>}
          {!diffLoading && !diffData && <div className="graph-diff-state"><History size={18} /><span>Choose two versions and run a comparison to inspect parameter and code changes.</span></div>}
          {diffData && (
            <div className="graph-diff-results">
              <section className="graph-diff-section">
                <div className="graph-diff-section__heading"><h4>Parameter modifications</h4><span>{Object.keys(diffData.parameter_changes || {}).length} CHANGES</span></div>
                {Object.keys(diffData.parameter_changes || {}).length ? (
                  <div className="graph-diff-table-wrap"><table className="graph-diff-table"><thead><tr><th>Parameter</th><th>{diffData.from_version || fromVer} · OLD</th><th>{diffData.to_version || toVer} · NEW</th></tr></thead><tbody>{Object.entries(diffData.parameter_changes).map(([key, change]) => <tr key={key}><td>{key}</td><td className="graph-diff-old">{String(change.old)}</td><td className="graph-diff-new">{String(change.new)}</td></tr>)}</tbody></table></div>
                ) : <p className="graph-diff-empty">No parameter differences detected.</p>}
              </section>
              {Object.keys(diffData.code_changes || {}).length > 0 && <section className="graph-diff-section"><div className="graph-diff-section__heading"><h4>Code modifications</h4><span>{Object.keys(diffData.code_changes).length} NODES</span></div>{Object.entries(diffData.code_changes).map(([nodeId, change]) => <div className="graph-diff-code" key={nodeId}><p><FileCode2 size={13} />{nodeId}</p><pre>{change.unified_diff || 'No code changes'}</pre></div>)}</section>}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}

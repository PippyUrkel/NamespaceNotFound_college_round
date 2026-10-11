import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, BookOpen, Bot, Check, ChevronDown, Copy, FileText, FlaskConical, MessageSquareText, RotateCcw, Sparkles, UserRound, X } from 'lucide-react';
import { api } from '../api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './OverviewTab.css';

const PROMPTS = [
  ['What is this paper about?', 'Research goal, approach, and main contribution.'],
  ['How was the model trained?', 'Dataset, training procedure, and parameters.'],
  ['Which optimizer was used?', 'Separate reported facts from inference.'],
  ['What are the limitations?', 'Caveats and missing experimental details.'],
];

function Answer({ text }) {
  return (
    <div className="overview-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener" />
          ),
          table: ({ node, ...props }) => (
            <div className="overview-table-wrap">
              <table {...props} />
            </div>
          ),
          pre: ({ node, ...props }) => (
            <pre className="overview-code-block" {...props} />
          ),
        }}
      >
        {String(text ?? '').trim()}
      </ReactMarkdown>
    </div>
  );
}
function Sources({ matches, onCopy }) {
  const [open, setOpen] = useState(true);
  if (!matches?.length) return null;
  return <section className="overview-sources">
    <button className="overview-sources-toggle" type="button" onClick={() => setOpen(v => !v)}>
      <span><FileText size={14} /> Retrieved sources <b>{matches.length}</b></span><ChevronDown size={15} className={open ? 'is-open' : ''} />
    </button>
    {open && <div className="overview-source-grid">{matches.map((m, i) => {
      const meta = m?.metadata || {};
      const id = meta.evidence_id || m?.id || `chunk-${i + 1}`;
      const excerpt = m?.text || m?.content || m?.chunk || 'No excerpt available.';
      return <article className="overview-source-card" key={id}>
        <div className="overview-source-head"><FileText size={14} /><span>{String(m?.source_type || meta.source_type || 'retrieved chunk').replaceAll('_', ' ').toUpperCase()}</span>{typeof m?.score === 'number' && <code>{m.score.toFixed(3)}</code>}</div>
        <p>{excerpt}</p>
        <div className="overview-source-foot"><span title={id}>{String(id).length > 24 ? `${String(id).slice(0, 21)}…` : id}</span><button type="button" onClick={() => onCopy(excerpt)}><Copy size={12} /> Copy excerpt</button></div>
      </article>;
    })}</div>}
  </section>;
}

export default function OverviewTab({ experimentId, experiment, spec }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [topK, setTopK] = useState(7);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const requestRef = useRef(0);
  const title = experiment?.name || experiment?.title || experiment?.paper_title || spec?.paper_title || spec?.title || 'Research paper';

  useEffect(() => { setMessages([]); setQuestion(''); setError(''); }, [experimentId]);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [messages, loading]);

  const copy = useCallback(async text => {
    try {
      await navigator.clipboard.writeText(String(text ?? ''));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { setError('Clipboard access was blocked. Select and copy the excerpt manually.'); }
  }, []);

  const ask = useCallback(async (raw = question) => {
    const q = String(raw || '').trim();
    if (!q || loading || !experimentId) return;
    const id = ++requestRef.current;
    setMessages(prev => [...prev, { id: `u-${Date.now()}`, role: 'user', content: q }]);
    setQuestion('');
    setError('');
    setLoading(true);
    try {
      const data = await api.retrieveResearch(experimentId, q, topK);
      if (id !== requestRef.current) return;
      const matches = Array.isArray(data?.matches)
        ? data.matches
        : Array.isArray(data?.results)
          ? data.results
          : Array.isArray(data?.chunks)
            ? data.chunks
            : [];
      const answer = data?.answer ?? data?.response ?? data?.message ?? 'The retrieval service returned no answer field.';
      setMessages(prev => [...prev, { id: `a-${Date.now()}`, role: 'assistant', content: String(answer), matches, namespace: data?.namespace }]);
    } catch (err) {
      if (id === requestRef.current) setError(err?.message || 'Could not reach the research retrieval service.');
    } finally {
      if (id === requestRef.current) setLoading(false);
    }
  }, [experimentId, loading, question, topK]);

  const submit = e => { e.preventDefault(); ask(); };
  const reset = () => { requestRef.current++; setMessages([]); setQuestion(''); setError(''); setLoading(false); inputRef.current?.focus(); };

  return <div className="overview-workspace">
    <header className="overview-header">
      <div>
        <div className="overview-kicker"><span /> RESEARCH ASSISTANT / RAG RETRIEVAL</div>
        <h2>Experiment <em>overview.</em></h2>
        <p>Ask questions about the ingested paper. Answers are grounded in retrieved research chunks, with source excerpts available for inspection.</p>
      </div>
      <div className="overview-header-actions">
        <div className="overview-paper-chip"><BookOpen size={14} /><span title={title}>{title}</span></div>
        <button className="overview-reset" type="button" onClick={reset} disabled={!messages.length && !error} title="Clear conversation" aria-label="Clear conversation"><RotateCcw size={15} /></button>
      </div>
    </header>

    <section className="overview-chat">
      <div className="overview-chat-top">
        <div className="overview-bot-id"><span><FlaskConical size={17} /></span><div><strong>Paper companion</strong><small>Context-aware retrieval · {experimentId ? `Experiment ${String(experimentId).slice(0, 8)}` : 'No experiment selected'}</small></div></div>
        <label className="overview-topk">Sources per answer
          <select value={topK} onChange={e => setTopK(Number(e.target.value))} disabled={loading}><option value={3}>3 chunks</option><option value={5}>5 chunks</option><option value={7}>7 chunks</option><option value={10}>10 chunks</option></select>
        </label>
      </div>

      <div className="overview-conversation" ref={scrollRef} aria-live="polite">
        {!messages.length ? <div className="overview-welcome">
          <span className="overview-welcome-icon"><Sparkles size={22} /></span>
          <small>YOUR PAPER, IN CONTEXT</small>
          <h3>What would you like to understand?</h3>
          <p>Start with a suggested question or ask something specific. The backend retrieves relevant paper chunks for each question.</p>
          <div className="overview-prompts">{PROMPTS.map(([label, detail]) => <button type="button" key={label} onClick={() => ask(label === 'How was the model trained?' ? 'How was the model trained? Include the dataset, training procedure, and parameters reported in the paper.' : label === 'Which optimizer was used?' ? 'Which optimizer was used? Distinguish what is explicitly reported by the paper from anything inferred.' : label === 'What are the limitations?' ? 'What limitations, assumptions, or missing experimental details are mentioned or evident in the retrieved paper excerpts?' : 'What is this paper about? Summarize its research goal, approach, and main contribution.')} disabled={!experimentId || loading}><strong>{label}</strong><span>{detail}</span><b>↗</b></button>)}</div>
        </div> : <div className="overview-messages">
          {messages.map(msg => <article className={`overview-message overview-message-${msg.role}`} key={msg.id}>
            <span className={`overview-message-icon ${msg.role === 'assistant' ? 'is-bot' : ''}`}>{msg.role === 'assistant' ? <Bot size={16} /> : <UserRound size={16} />}</span>
            <div className="overview-message-body">
              <div className="overview-message-meta"><strong>{msg.role === 'assistant' ? 'Paper companion' : 'You'}</strong>{msg.namespace && <small>{msg.namespace}</small>}{msg.role === 'assistant' && <button type="button" title="Copy answer" onClick={() => copy(msg.content)}>{copied ? <Check size={12} /> : <Copy size={12} />}</button>}</div>
              {msg.role === 'assistant' ? <><Answer text={msg.content} /><Sources matches={msg.matches} onCopy={copy} /></> : <p className="overview-user-text">{msg.content}</p>}
            </div>
          </article>)}
          {loading && <article className="overview-message"><span className="overview-message-icon is-bot"><Bot size={16} /></span><div className="overview-message-body"><div className="overview-message-meta"><strong>Paper companion</strong><small>Retrieving evidence</small></div><div className="overview-loading"><i /><i /><i /> Searching the paper chunks…</div></div></article>}
        </div>}
      </div>

      {error && <div className="overview-error" role="alert"><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Dismiss error"><X size={14} /></button></div>}
      <form className="overview-composer" onSubmit={submit}>
        <div className="overview-input-wrap"><MessageSquareText size={17} /><textarea ref={inputRef} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(e); } }} placeholder={experimentId ? 'Ask a question about the paper…' : 'Select an experiment to begin…'} rows={1} disabled={!experimentId || loading} aria-label="Ask a question about the paper" /><button type="submit" disabled={!question.trim() || !experimentId || loading} aria-label="Send question"><ArrowUp size={17} /></button></div>
        <div className="overview-composer-note"><span><i /> Answers use retrieved chunks; verify important claims against the source.</span><span>Enter to send · Shift + Enter for a new line</span></div>
      </form>
    </section>
  </div>;
}

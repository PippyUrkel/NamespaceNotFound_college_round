import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {

  ShieldAlert, ShieldCheck, FileText, Play, RefreshCw, Download,

  CheckCircle2, XCircle, HelpCircle, AlertTriangle, Scale,

  ClipboardCheck, Activity, ExternalLink,

} from 'lucide-react';

import { api } from '../api';

import './AuditTab.css';

const VERDICT_STYLES = {

  Reproducible: { tone: 'success', Icon: CheckCircle2 },

  'Not reproducible': { tone: 'conflict', Icon: XCircle },

  'Not verifiable': { tone: 'assumed', Icon: HelpCircle },

  'Pending verification': { tone: 'research', Icon: HelpCircle },

};

const CLAIM_BADGES = {

  reproducible: ['success', 'Reproducible'],

  not_reproducible: ['conflict', 'Not reproducible'],

  not_verifiable: ['assumed', 'Not verifiable'],

};

const SEVERITY_BADGES = {

  critical: 'conflict',

  high: 'assumed',

  medium: 'code',

  low: 'neutral',

};

function fmt(value, digits = 4) {

  if (value == null || Number.isNaN(Number(value))) return '—';

  return String(parseFloat(Number(value).toPrecision(digits)));

}

function evidenceLabel(evidence) {

  const location = [

    evidence.section,

    evidence.file_path,

    evidence.page_number ? `page ${evidence.page_number}` : null,

    evidence.url,

  ].filter(Boolean).join(', ');

  return `${evidence.source || 'Evidence'}${location ? ` (${location})` : ''}`;

}

function SectionHeading({ icon: Icon, eyebrow, children, trailing }) {

  return (

    <div className="audit-section-heading">

      <div className="audit-section-heading-main">

        <span className="audit-section-icon"><Icon size={17} /></span>

        <div>

          {eyebrow && <div className="audit-eyebrow">{eyebrow}</div>}

          <h3>{children}</h3>

        </div>

      </div>

      {trailing}

    </div>

  );

}

export default function AuditTab({ experimentId, latestExecution }) {

  const [audit, setAudit] = useState(null);

  const [report, setReport] = useState(null);

  const [busy, setBusy] = useState('');

  const [error, setError] = useState('');

  const [includeLlm, setIncludeLlm] = useState(true);
  const [reportMarkdown, setReportMarkdown] = useState('');
  const [markdownLoading, setMarkdownLoading] = useState(false);
  const [markdownError, setMarkdownError] = useState('');

  useEffect(() => {

    setAudit(null);

    setReport(null);

    setError('');

    loadAll();

    // eslint-disable-next-line react-hooks/exhaustive-deps

  }, [experimentId]);

  useEffect(() => {
    let cancelled = false;

    async function loadMarkdown() {
      if (!report) {
        setReportMarkdown('');
        setMarkdownError('');
        return;
      }

      setMarkdownLoading(true);
      setMarkdownError('');

      try {
        const response = await fetch(api.getReportMarkdownUrl(experimentId), {
          headers: { Accept: 'text/markdown, text/plain;q=0.9, */*;q=0.1' },
          credentials: 'same-origin',
        });

        if (!response.ok) {
          throw new Error(`Report preview request failed (${response.status}).`);
        }

        const markdown = await response.text();
        if (!cancelled) {
          // Avoid showing an HTML error page as if it were a Markdown report.
          const looksLikeHtml = /^\\s*<!doctype html|^\\s*<html[\\s>]/i.test(markdown);
          if (looksLikeHtml) {
            throw new Error('The report endpoint returned HTML instead of Markdown.');
          }
          setReportMarkdown(markdown);
        }
      } catch (exception) {
        if (!cancelled) {
          setReportMarkdown('');
          setMarkdownError(exception?.message || 'Could not load the Markdown preview.');
        }
      } finally {
        if (!cancelled) setMarkdownLoading(false);
      }
    }

    loadMarkdown();
    return () => { cancelled = true; };
  }, [experimentId, report?.generated_at, report?.verdict?.status]);

  async function loadAll() {

    try {

      setAudit(await api.getAudit(experimentId));

    } catch {

      setAudit(null);

    }

    try {

      setReport(await api.getReport(experimentId));

    } catch {

      setReport(null);

    }

  }

  async function run(label, action) {

    setBusy(label);

    setError('');

    try {

      await action();

      await loadAll();

    } catch (exception) {

      setError(exception?.message || 'The requested audit action failed.');

    } finally {

      setBusy('');

    }

  }

  const verification = audit?.claim_verification || report?.claim_verification;

  const verdict = report?.verdict;

  const verdictStyle =

    VERDICT_STYLES[verdict?.status] || VERDICT_STYLES['Pending verification'];

  const VerdictIcon = verdictStyle.Icon;

  const findings = report?.findings || audit?.findings || [];

  const risk = report?.risk_score || audit?.risk_score;

  const auditedExecution = audit?.run?.execution_id;

  const runAuditStale =

    latestExecution && auditedExecution !== latestExecution.execution_id;

  return (

    <div className="audit-workspace">

      <section className="audit-intro">

        <div>

          <div className="audit-eyebrow audit-intro-kicker">

            <span className="audit-live-dot" />

            VALIDATION / REPORTING

          </div>

          <h2>Audit & <span>report.</span></h2>

          <p>

            Evaluate paper claims against reproduced results and inspect

            the evidence behind every finding.

          </p>

        </div>

        <div className="audit-intro-mark" aria-hidden="true">

          <ShieldCheck size={28} />

          <span>CG / AUDIT</span>

        </div>

      </section>

      <section className="audit-toolbar audit-panel">

        <div className="audit-toolbar-copy">

          <span className="audit-eyebrow">AUDIT CONTROLS</span>

          <span className="audit-toolbar-caption">

            Run checks, compare results, and generate a reproducibility report.

          </span>

        </div>

        <div className="audit-toolbar-actions">

          <button

            className="audit-btn audit-btn-secondary"

            disabled={Boolean(busy)}

            onClick={() =>

              run('static', () => api.runStaticAudit(experimentId, includeLlm))

            }

          >

            <ShieldAlert size={15} />

            {busy === 'static' ? 'Auditing…' : 'Run static audit'}

          </button>

          <label className="audit-checkbox-label">

            <input

              type="checkbox"

              checked={includeLlm}

              onChange={(event) => setIncludeLlm(event.target.checked)}

            />

            <span>Include LLM checks</span>

          </label>

          <button

            className="audit-btn audit-btn-secondary"

            disabled={Boolean(busy) || !latestExecution}

            title={

              latestExecution

                ? ''

                : 'Run the experiment in the Execution Runner tab first'

            }

            onClick={() =>

              run('run', () =>

                api.runRunAudit(experimentId, latestExecution?.execution_id)

              )

            }

          >

            <Play size={14} />

            {busy === 'run' ? 'Comparing…' : 'Compare latest run'}

          </button>

          <button

            className="audit-btn audit-btn-primary"

            disabled={Boolean(busy)}

            onClick={() => run('report', () => api.generateReport(experimentId))}

          >

            <FileText size={15} />

            {busy === 'report' ? 'Generating…' : 'Generate report'}

          </button>

          <button

            className="audit-icon-btn"

            disabled={Boolean(busy)}

            onClick={() => run('refresh', loadAll)}

            aria-label="Refresh audit data"

            title="Refresh audit data"

          >

            <RefreshCw

              size={15}

              className={busy === 'refresh' ? 'audit-spin' : ''}

            />

          </button>

          {report && (

            <a

              className="audit-btn audit-btn-secondary"

              href={api.getReportMarkdownUrl(experimentId)}

              target="\_blank"

              rel="noreferrer"

            >

              <Download size={14} />

              report.md

              <ExternalLink size={12} />

            </a>

          )}

        </div>

        {runAuditStale && (

          <div className="audit-notice audit-notice-assumed">

            <AlertTriangle size={14} />

            Latest run <code>{latestExecution.execution_id}</code> has not yet

            been compared with the paper.

          </div>

        )}

      </section>

      {error && (

        <div className="audit-notice audit-notice-conflict" role="alert">

          <AlertTriangle size={15} />

          <span>{error}</span>

        </div>

      )}

      <section className="audit-verdict-layout">

        <div className={`audit-verdict-card audit-tone-${verdictStyle.tone}`}>

          <div className="audit-verdict-topline">

            <span className="audit-eyebrow">OVERALL VERDICT</span>

            <span className="audit-status-chip">

              <VerdictIcon size={13} />

              {verdict?.status || 'Pending verification'}

            </span>

          </div>

          <div className="audit-verdict-content">

            <span className="audit-verdict-icon">

              <VerdictIcon size={25} />

            </span>

            <div>

              <h3>{verdict ? verdict.status : 'Report not generated'}</h3>

              <p>

                {verdict

                  ? 'Review the reasons and supporting evidence before treating this result as verified.'

                  : 'Generate a report to evaluate reproducibility and compare the latest execution with the paper claims.'}

              </p>

            </div>

          </div>

          {verdict?.reasons?.length > 0 && (

            <ul className="audit-verdict-reasons">

              {verdict.reasons.map((reason, index) => (

                <li key={`${index}-${reason}`}>{reason}</li>

              ))}

            </ul>

          )}

          {report?.generated_at && (

            <div className="audit-generated-at">

              REPORT GENERATED / {new Date(report.generated_at).toLocaleString()}

            </div>

          )}

        </div>

        <div className="audit-risk-card audit-panel">

          <div className="audit-risk-header">

            <span className="audit-section-icon"><Activity size={17} /></span>

            <div>

              <div className="audit-eyebrow">REPRODUCIBILITY RISK</div>

              <h3>{risk ? `${risk.score}/100` : '—'}</h3>

            </div>

          </div>

          {risk ? (

            <>

              <div

                className="audit-risk-meter"

                role="img"

                aria-label={`Risk score ${risk.score} out of 100`}

              >

                <span

                  style={{

                    width: `${Math.max(0, Math.min(100, Number(risk.score) || 0))}%`,

                  }}

                />

              </div>

              <div className="audit-risk-footer">

                <span>Risk score</span>

                <strong className={`audit-risk-${risk.bucket || 'medium'}`}>

                  {risk.bucket || 'Unclassified'}

                </strong>

              </div>

            </>

          ) : (

            <p className="audit-muted-copy">

              Run an audit to calculate the current risk score.

            </p>

          )}

        </div>

      </section>

      <section className="audit-panel audit-section-panel">

        <SectionHeading

          icon={Scale}

          eyebrow="CLAIM VERIFICATION"

          trailing={

            verification && (

              <span className="audit-meta-chip">

                Tolerance ±{Math.round((verification.tolerance || 0.1) * 100)}%

              </span>

            )

          }

        >

          Paper claims vs reproduced results

        </SectionHeading>

        {!verification ? (

          <div className="audit-empty-inline">

            <div className="audit-empty-icon"><Scale size={19} /></div>

            <div>

              <strong>No comparison available</strong>

              <p>Run the experiment, then compare the latest run with the paper.</p>

            </div>

          </div>

        ) : verification.claims?.length === 0 ? (

          <div className="audit-empty-inline">

            <div className="audit-empty-icon"><HelpCircle size={19} /></div>

            <div>

              <strong>No verifiable claims found</strong>

              <p>

                {verification.reasons?.join(' ') ||

                  'The current report does not contain metric claims to compare.'}

              </p>

            </div>

          </div>

        ) : (

          <div className="audit-table-wrap">

            <table className="audit-table">

              <thead>

                <tr>

                  <th>Metric</th>

                  <th>Claimed <span>/ PAPER</span></th>

                  <th>Reproduced <span>/ MEAN ± STD</span></th>

                  <th>Gap</th>

                  <th>Verdict</th>

                </tr>

              </thead>

              <tbody>

                {verification.claims.map((claim, index) => {

                  const [tone, label] =

                    CLAIM_BADGES[claim.verdict] || CLAIM_BADGES.not_verifiable;

                  return (

                    <tr key={`${claim.metric || 'metric'}-${index}`}>

                      <td className="audit-metric-cell">

                        <strong>{claim.metric}</strong>

                        {claim.claim_quote && (

                          <p className="audit-claim-quote">

                            “{claim.claim_quote}”

                          </p>

                        )}

                      </td>

                      <td>

                        <span className="audit-number">

                          {fmt(claim.claimed_value)}

                        </span>

                      </td>

                      <td>

                        <span className="audit-number">

                          {fmt(claim.reproduced_mean)}

                          {claim.reproduced_std != null

                            ? ` ± ${fmt(claim.reproduced_std, 2)}`

                            : ''}

                        </span>

                        <span className="audit-cell-subtext">

                          {claim.seeds_run ?? 0} seed(s)

                        </span>

                      </td>

                      <td>

                        <span className="audit-number">

                          {claim.gap != null

                            ? `${(claim.gap * 100).toFixed(1)}%`

                            : '—'}

                        </span>

                      </td>

                      <td>

                        <span className={`audit-chip audit-chip-${tone}`}>

                          {label}

                        </span>

                        {claim.used_assumed_values && (

                          <span className="audit-assumption-note">

                            Run used assumed values

                          </span>

                        )}

                      </td>

                    </tr>

                  );

                })}

              </tbody>

            </table>

          </div>

        )}

      </section>

            {verification?.claims?.some((claim) =>
        claim.claimed_value != null && claim.reproduced_mean != null &&
        Number.isFinite(Number(claim.claimed_value)) &&
        Number.isFinite(Number(claim.reproduced_mean))
      ) && (
        <section className="audit-panel audit-section-panel audit-visual-comparison">
          <SectionHeading icon={Activity} eyebrow="VISUAL COMPARISON"
            trailing={<span className="audit-meta-chip">PAPER vs REPRODUCTION</span>}>
            Accuracy &amp; metric comparison
          </SectionHeading>
          <p className="audit-chart-intro">
            Compare reported paper values with the mean from the reproduced run.
            Each pair is scaled within its metric for quick visual inspection.
          </p>
          <div className="audit-chart-legend" aria-label="Chart legend">
            <span><i className="audit-legend-paper" /> Paper claim</span>
            <span><i className="audit-legend-reproduced" /> Reproduced mean</span>
          </div>
          <div className="audit-comparison-list">
            {verification.claims.filter((claim) =>
              claim.claimed_value != null && claim.reproduced_mean != null &&
              Number.isFinite(Number(claim.claimed_value)) &&
              Number.isFinite(Number(claim.reproduced_mean))
            ).map((claim, index) => {
              const paperValue = Number(claim.claimed_value);
              const reproducedValue = Number(claim.reproduced_mean);
              const scaleMax = Math.max(Math.abs(paperValue), Math.abs(reproducedValue), 0.000001);
              const paperWidth = Math.abs(paperValue) / scaleMax * 100;
              const reproducedWidth = Math.abs(reproducedValue) / scaleMax * 100;
              const gapText = claim.gap != null ? `${(Number(claim.gap) * 100).toFixed(1)}%` : '—';
              return (
                <article className="audit-comparison-item" key={`visual-${claim.metric || 'metric'}-${index}`}>
                  <div className="audit-comparison-heading">
                    <strong>{claim.metric || `Metric ${index + 1}`}</strong>
                    <span className={`audit-comparison-gap ${claim.verdict === 'reproducible' ? 'is-close' : claim.verdict === 'not_reproducible' ? 'is-gap' : ''}`}>
                      Gap <b>{gapText}</b>
                    </span>
                  </div>
                  <div className="audit-comparison-row">
                    <span className="audit-comparison-label">Paper</span>
                    <div className="audit-comparison-track"><span className="audit-comparison-bar is-paper" style={{ width: `${paperWidth}%` }} /></div>
                    <code>{fmt(paperValue)}</code>
                  </div>
                  <div className="audit-comparison-row">
                    <span className="audit-comparison-label">Run mean</span>
                    <div className="audit-comparison-track"><span className="audit-comparison-bar is-reproduced" style={{ width: `${reproducedWidth}%` }} /></div>
                    <code>{fmt(reproducedValue)}</code>
                  </div>
                  {claim.reproduced_std != null && (
                    <div className="audit-comparison-variance">
                      Across {claim.seeds_run ?? 0} seed(s) · standard deviation ±{fmt(claim.reproduced_std, 3)}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}

<section className="audit-panel audit-section-panel">

        <SectionHeading

          icon={ShieldCheck}

          eyebrow="FINDINGS & REMEDIATION"

          trailing={

            <span className="audit-count-chip">

              {findings.length} finding{findings.length === 1 ? '' : 's'}

            </span>

          }

        >

          Reproducibility audit findings

        </SectionHeading>

        {!audit && !report ? (

          <div className="audit-empty-inline">

            <div className="audit-empty-icon"><ClipboardCheck size={19} /></div>

            <div>

              <strong>No audit has been run</strong>

              <p>

                Run a static audit to surface missing configuration, evidence

                gaps, and reproducibility risks.

              </p>

            </div>

          </div>

        ) : findings.length === 0 ? (

          <div className="audit-empty-inline">

            <div className="audit-empty-icon audit-empty-success">

              <CheckCircle2 size={19} />

            </div>

            <div>

              <strong>No findings reported</strong>

              <p>No findings were returned by the current audit or report.</p>

            </div>

          </div>

        ) : (

          <div className="audit-findings-list">

            {findings.map((finding, index) => (

              <article

                className="audit-finding"

                key={`${finding.title || 'finding'}-${index}`}

              >

                <div className="audit-finding-accent" />

                <div className="audit-finding-body">

                  <div className="audit-finding-topline">

                    <span

                      className={`audit-chip audit-chip-${

                        SEVERITY_BADGES[finding.severity] || 'neutral'

                      }`}

                    >

                      {finding.severity || 'unknown'}

                    </span>

                    <span className="audit-chip audit-chip-neutral">

                      {finding.status || 'unresolved'}

                    </span>

                    <span className="audit-chip audit-chip-neutral">

                      {finding.phase || 'general'}

                    </span>

                    <h4>{finding.title}</h4>

                  </div>

                  <p className="audit-finding-message">{finding.message}</p>

                  {finding.evidence?.length > 0 && (

                    <div className="audit-evidence-block">

                      <div className="audit-eyebrow">SUPPORTING EVIDENCE</div>

                      <ul>

                        {finding.evidence.map((evidence, evidenceIndex) => (

                          <li

                            key={`${evidence.source || 'evidence'}-${evidenceIndex}`}

                          >

                            <span className="audit-evidence-source">

                              {evidenceLabel(evidence)}

                            </span>

                            {evidence.exact_text && (

                              <blockquote>

                                “{evidence.exact_text.slice(0, 200)}”

                              </blockquote>

                            )}

                          </li>

                        ))}

                      </ul>

                    </div>

                  )}

                  {finding.remediation && (

                    <div className="audit-remediation">

                      <strong>Recommended remediation</strong>

                      <p>{finding.remediation}</p>

                    </div>

                  )}

                </div>

              </article>

            ))}

          </div>

        )}

      </section>

      {report && (
        <section className="audit-panel audit-report-panel">
          <div className="audit-report-toolbar">
            <div className="audit-report-heading">
              <span className="audit-section-icon"><FileText size={17} /></span>
              <div>
                <div className="audit-eyebrow">GENERATED DOCUMENT / MARKDOWN</div>
                <h3>Audit report</h3>
                <p>Rendered preview of the generated report. The original Markdown remains available to download.</p>
              </div>
            </div>
            <div className="audit-report-actions">
              <span className="audit-report-format">.MD SOURCE</span>
              <button
                className="audit-btn audit-btn-secondary"
                type="button"
                onClick={() => window.print()}
                disabled={!reportMarkdown.trim() || markdownLoading}
                title="Open the print dialog, then choose Save as PDF"
              >
                <FileText size={14} /> Export PDF
              </button>
              <a
                className="audit-btn audit-btn-secondary"
                href={api.getReportMarkdownUrl(experimentId)}
                target="_blank"
                rel="noreferrer"
              >
                <Download size={14} /> Download source
              </a>
            </div>
          </div>

          <div className="audit-report-reader">
            {markdownLoading ? (
              <div className="audit-report-state">
                <RefreshCw size={17} className="audit-spin" />
                <span>Loading report preview…</span>
              </div>
            ) : markdownError ? (
              <div className="audit-report-state audit-report-state--error" role="status">
                <AlertTriangle size={17} />
                <div>
                  <strong>Preview unavailable</strong>
                  <p>{markdownError}</p>
                  <p>The report can still be opened or downloaded using the source link above.</p>
                </div>
              </div>
            ) : reportMarkdown.trim() ? (
              <article className="audit-markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ node, ...props }) => (
                      <a {...props} target="_blank" rel="noreferrer" />
                    ),
                    pre: ({ children, ...props }) => <pre {...props}>{children}</pre>,
                    table: ({ children, ...props }) => (
                      <div className="audit-markdown-table-wrap">
                        <table {...props}>{children}</table>
                      </div>
                    ),
                  }}
                >
                  {reportMarkdown}
                </ReactMarkdown>
              </article>
            ) : (
              <div className="audit-report-state">
                <FileText size={18} />
                <div>
                  <strong>No Markdown content returned</strong>
                  <p>Generate the report again or open the original source file.</p>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {report?.limitations?.length > 0 && (

        <section className="audit-panel audit-section-panel">

          <SectionHeading icon={AlertTriangle} eyebrow="SCOPE & CAVEATS">

            Limitations of this report

          </SectionHeading>

          <ul className="audit-limitations-list">

            {report.limitations.map((limitation, index) => (

              <li key={`${index}-${limitation}`}>{limitation}</li>

            ))}

          </ul>

        </section>

      )}

    </div>

  );

}

import { useState, useRef, useCallback, useEffect } from "react";
import "./App.css";

// Same-origin when served by the FastAPI container (VITE_API_BASE=""), dev server otherwise.
const API = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

const REVIEW_CONFIG = {
  pass: { label: "Resolution reviewed", color: "#16A34A", bg: "#F0FDF4" },
  flag: { label: "Review flagged this resolution", color: "#D97706", bg: "#FFFBEB" },
  hide: { label: "Resolution withheld", color: "#DC2626", bg: "#FEF2F2" },
};

const RISK_CONFIG = {
  CRITICAL: { color: "#DC2626", bg: "#FEF2F2", border: "#FECACA", label: "Critical" },
  HIGH:     { color: "#EA580C", bg: "#FFF7ED", border: "#FED7AA", label: "High"     },
  MEDIUM:   { color: "#D97706", bg: "#FFFBEB", border: "#FDE68A", label: "Medium"   },
  LOW:      { color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0", label: "Low"      },
};

function UploadZone({ label, file, onFile, color, disabled = false }) {
  const inputRef = useRef();
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type === "application/pdf") onFile(f);
  }, [onFile]);

  return (
    <div
      className={`upload-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""} ${disabled ? "disabled" : ""}`}
      style={{ "--zone-color": color }}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={disabled ? (e) => e.preventDefault() : handleDrop}
      onClick={() => !file && !disabled && inputRef.current?.click()}
      title={disabled ? "Uploads are switched off in demo replay mode" : undefined}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={(e) => e.target.files[0] && onFile(e.target.files[0])}
      />
      <div className="upload-icon">
        {file ? (
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="9" y1="13" x2="15" y2="13"/>
            <line x1="9" y1="17" x2="15" y2="17"/>
          </svg>
        ) : (
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17,8 12,3 7,8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
        )}
      </div>
      <div className="upload-label">{label}</div>
      {file ? (
        <div className="upload-filename">{file.name}</div>
      ) : (
        <div className="upload-hint">{disabled ? "Uploads off in demo mode" : "Drop PDF here or click to browse"}</div>
      )}
      {file && (
        <button
          className="upload-remove"
          onClick={(e) => { e.stopPropagation(); onFile(null); }}
        >
          ✕ Remove
        </button>
      )}
    </div>
  );
}

// Live feed of the agent's tool calls (the agentic loop made visible). Each `tool` SSE event is one row.
function ToolFeed({ tools }) {
  if (!tools.length) return null;
  return (
    <div className="tool-feed">
      <div className="tool-feed-title">Agent tool calls · {tools.length}</div>
      <ol className="tool-feed-list">
        {tools.map((t, i) => (
          <li key={i} className={i === tools.length - 1 ? "latest" : ""}>
            <code>{t.name}</code>
            {t.summary && <span className="tool-feed-summary">{t.summary}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function ProgressBar({ steps, currentStep, message }) {
  return (
    <div className="progress-container">
      <div className="progress-steps">
        {steps.map((step, i) => (
          <div key={i} className={`progress-step ${i < currentStep ? "done" : i === currentStep ? "active" : ""}`}>
            <div className="progress-dot">
              {i < currentStep ? (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              ) : (
                <span>{i + 1}</span>
              )}
            </div>
            <div className="progress-step-label">{step}</div>
          </div>
        ))}
      </div>
      <div className="progress-message">{message}</div>
    </div>
  );
}

function SummaryBar({ summary, total }) {
  return (
    <div className="summary-bar">
      <div className="summary-total">
        <span className="summary-num">{total}</span>
        <span className="summary-text">conflicts found</span>
      </div>
      <div className="summary-badges">
        {Object.entries(RISK_CONFIG).map(([risk, cfg]) => (
          summary[risk] > 0 && (
            <div key={risk} className="summary-badge" style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color }}>
              <span className="badge-num">{summary[risk]}</span>
              <span className="badge-label">{cfg.label}</span>
            </div>
          )
        ))}
      </div>
    </div>
  );
}

function ConflictCard({ conflict, index, forceOpen = false }) {
  const [expanded, setExpanded] = useState(forceOpen || index === 0);
  const cfg = RISK_CONFIG[conflict.risk] || RISK_CONFIG.LOW;

  return (
    <div className="conflict-card" style={{ "--risk-color": cfg.color, "--risk-bg": cfg.bg, "--risk-border": cfg.border }}>
      <div className="conflict-header" onClick={() => setExpanded(!expanded)}>
        <div className="conflict-left">
          <span className="conflict-risk-badge" style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}>
            {cfg.label}
          </span>
          <span className="conflict-topic">{conflict.topic}</span>
        </div>
        <div className="conflict-right">
          <span className={`conflict-favor-badge ${conflict.favor === "Company" ? "favor-us" : "favor-them"}`}
            title={conflict.favor === "Company"
              ? "The model judged your standard clause more protective of you than the vendor's proposal: push to keep it."
              : "The model judged the vendor's proposed clause acceptable or better for you: consider accepting it."}>
            {conflict.favor === "Company" ? "Keep your clause" : "Vendor's version acceptable"}
          </span>
          <span className={`conflict-chevron ${expanded ? "open" : ""}`}>›</span>
        </div>
      </div>

      {expanded && (
        <div className="conflict-body">
          <div className="clause-comparison">
            <div className="clause-side company">
              <div className="clause-side-label">Your Contract</div>
              <div className="clause-section-ref">{conflict.company_section}</div>
              <div className="clause-text">"{conflict.company_text}"</div>
            </div>
            <div className="clause-vs">VS</div>
            <div className="clause-side vendor">
              <div className="clause-side-label">Vendor Contract</div>
              <div className="clause-section-ref">{conflict.vendor_section}</div>
              <div className="clause-text">"{conflict.vendor_text}"</div>
            </div>
          </div>

          <div className="conflict-explanation">
            <div className="explanation-label">Why This Conflicts</div>
            <p>{conflict.conflict_explanation}</p>
          </div>

          <div className="conflict-resolution">
            <div className="resolution-label">Suggested Resolution</div>
            <p>{conflict.resolution}</p>
            {conflict.resolution_review && (
              <div className="resolution-review" style={{ color: REVIEW_CONFIG[conflict.resolution_review.verdict]?.color, background: REVIEW_CONFIG[conflict.resolution_review.verdict]?.bg }}>
                <strong>{REVIEW_CONFIG[conflict.resolution_review.verdict]?.label || "Reviewed"}</strong>
                {conflict.resolution_review.reason && <span> · {conflict.resolution_review.reason}</span>}
              </div>
            )}
            {conflict.playbook_ref && (
              <div className="playbook-ref">Grounded in playbook entry <code>{conflict.playbook_ref}</code></div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterBar({ active, onChange, counts }) {
  return (
    <div className="filter-bar">
      <button className={`filter-btn ${active === "ALL" ? "active" : ""}`} onClick={() => onChange("ALL")}>
        All
      </button>
      {Object.entries(RISK_CONFIG).map(([risk, cfg]) => (
        counts[risk] > 0 && (
          <button
            key={risk}
            className={`filter-btn ${active === risk ? "active" : ""}`}
            style={active === risk ? { background: cfg.bg, color: cfg.color, borderColor: cfg.border } : {}}
            onClick={() => onChange(risk)}
          >
            {cfg.label} ({counts[risk]})
          </button>
        )
      ))}
    </div>
  );
}

export default function App() {
  const [contractA, setContractA] = useState(null);
  const [contractB, setContractB] = useState(null);
  const [phase, setPhase] = useState("upload"); // upload | analyzing | results | error
  const [progressStep, setProgressStep] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [report, setReport] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [errorMsg, setErrorMsg] = useState("");

  const STEPS = ["Extract Clauses", "Choose Strategy", "Find Conflicts", "Review Resolutions", "Complete"];
  const [pdfLoading, setPdfLoading] = useState(false);
  const [serverConfig, setServerConfig] = useState(null);
  const [governingLaw, setGoverningLaw] = useState("");
  const [routeInfo, setRouteInfo] = useState(null);
  const [traceInfo, setTraceInfo] = useState(null);
  const [judgeInfo, setJudgeInfo] = useState(null);
  const [notices, setNotices] = useState([]);
  const [tools, setTools] = useState([]);
  const [demoRecordedAt, setDemoRecordedAt] = useState(null);
  const [expandAll, setExpandAll] = useState(false);

  useEffect(() => {
    fetch(`${API}/config`).then((r) => r.ok ? r.json() : null).then(setServerConfig).catch(() => setServerConfig(null));
  }, []);

  const runAnalysis = async (demo = false) => {
    if (!demo && (!contractA || !contractB)) return;

    setPhase("analyzing");
    setProgressStep(0);
    setProgressMsg(demo ? "Replaying recorded analysis of the sample contracts..." : "Uploading contracts...");
    setReport(null);
    setRouteInfo(null);
    setTraceInfo(null);
    setJudgeInfo(null);
    setNotices([]);
    setTools([]);
    setDemoRecordedAt(null);
    setExpandAll(false);

    try {
      let streamUrl;
      if (demo) {
        streamUrl = `${API}/analyze/demo`;
      } else {
        const form = new FormData();
        form.append("contract_a", contractA);
        form.append("contract_b", contractB);
        const uploadRes = await fetch(`${API}/upload`, { method: "POST", body: form });
        if (!uploadRes.ok) {
          let detail = "Upload failed";
          try { detail = (await uploadRes.json()).detail || detail; } catch {}
          throw new Error(detail);
        }
        const { session_id } = await uploadRes.json();
        const params = governingLaw ? `?governing_law=${encodeURIComponent(governingLaw)}` : "";
        streamUrl = `${API}/analyze/${session_id}${params}`;
      }

      const evtSource = new EventSource(streamUrl);

      evtSource.addEventListener("status", (e) => {
        const data = JSON.parse(e.data);
        setProgressMsg(data.message);
        if (data.step !== undefined) setProgressStep(data.step);
        if (/injection|only the first/i.test(data.message)) setNotices((n) => [...n, data.message]);
      });

      evtSource.addEventListener("route", (e) => setRouteInfo(JSON.parse(e.data)));
      evtSource.addEventListener("tool", (e) => setTools((prev) => [...prev, JSON.parse(e.data)]));
      evtSource.addEventListener("judge", (e) => setJudgeInfo(JSON.parse(e.data)));
      evtSource.addEventListener("trace", (e) => setTraceInfo(JSON.parse(e.data)));

      evtSource.addEventListener("complete", (e) => {
        evtSource.close();
        const data = JSON.parse(e.data);
        setDemoRecordedAt(data.demo_recorded_at || null);
        setReport(data.report);
        setPhase("results");
      });

      evtSource.addEventListener("error", (e) => {
        evtSource.close();
        try {
          const data = JSON.parse(e.data);
          setErrorMsg(data.message || "Analysis failed");
        } catch {
          setErrorMsg("Connection error. Is the backend running?");
        }
        setPhase("error");
      });

      // Catches network drops, backend crashes, and timeouts —
      // distinct from the custom "error" SSE event above
      evtSource.onerror = () => {
        evtSource.close();
        setErrorMsg("Connection lost. Check that the backend is running on port 8000.");
        setPhase("error");
      };

    } catch (err) {
      setErrorMsg(err.message);
      setPhase("error");
    }
  };

  const downloadJSON = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "clauseguard-redline-brief.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const downloadPDF = async () => {
    setPdfLoading(true);
    try {
      const res = await fetch(`${API}/generate-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      });
      if (!res.ok) throw new Error("PDF generation failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "clauseguard-redline-brief.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      alert("PDF generation failed: " + err.message);
    } finally {
      setPdfLoading(false);
    }
  };

  const reset = () => {
    setContractA(null);
    setContractB(null);
    setPhase("upload");
    setReport(null);
    setFilter("ALL");
    setErrorMsg("");
    setProgressStep(0);
    setRouteInfo(null);
    setTraceInfo(null);
    setJudgeInfo(null);
    setNotices([]);
    setTools([]);
    setDemoRecordedAt(null);
    setExpandAll(false);
  };

  const filteredConflicts = report?.conflicts?.filter(
    (c) => filter === "ALL" || c.risk === filter
  ) || [];

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#1E3A5F" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="9" y1="13" x2="15" y2="13"/>
            <line x1="9" y1="17" x2="13" y2="17"/>
          </svg>
          <span className="header-brand">ClauseGuard</span>
        </div>
        <div className="header-tagline">Contract Conflict Detector</div>
        {phase !== "upload" && (
          <button className="header-reset" onClick={reset}>New Analysis</button>
        )}
      </header>

      <main className="app-main">

        {/* UPLOAD PHASE */}
        {phase === "upload" && (
          <div className="upload-phase">
            <div className="upload-hero">
              <h1>Find every conflict<br /><em>before you sign.</em></h1>
              <p>Upload two contracts. ClauseGuard's AI agent reads both, identifies every conflicting clause, ranks them by legal risk, and delivers a reviewed redline brief. A typical pair takes one to two minutes; the eval is in the README.</p>
            </div>

            {serverConfig?.demo && (
              <div className="demo-banner">
                <span><strong>Demo replay.</strong> This instance replays an analysis of the two sample contracts recorded
                  {serverConfig.demo_recorded_at ? ` on ${new Date(serverConfig.demo_recorded_at).toISOString().slice(0, 10)}` : " earlier"} with live model calls.
                  Uploads and the governing-law option are switched off; no model calls are made here.</span>
                <button className="demo-btn" onClick={() => runAnalysis(true)}>Run the recorded demo →</button>
              </div>
            )}

            <div className="upload-grid">
              <UploadZone
                label="Your Standard Contract"
                file={contractA}
                onFile={setContractA}
                color="#1E3A5F"
                disabled={!!serverConfig?.demo}
              />
              <div className="upload-vs-divider">
                <span>VS</span>
              </div>
              <UploadZone
                label="Vendor / Supplier Contract"
                file={contractB}
                onFile={setContractB}
                color="#7C3AED"
                disabled={!!serverConfig?.demo}
              />
            </div>

            <div className="options-row">
              <label className="option" title={serverConfig?.demo ? "Fixed in demo replay mode" : "Flags a conflict if either contract names a different governing law"}>
                <span>Expected governing law{serverConfig?.demo ? " (fixed in demo)" : ""}</span>
                <select value={governingLaw} onChange={(e) => setGoverningLaw(e.target.value)} disabled={!!serverConfig?.demo}>
                  {(serverConfig?.governing_law_options || ["", "New York", "Delaware", "California"]).map((o) => (
                    <option key={o} value={o}>{o || "Not specified"}</option>
                  ))}
                </select>
              </label>
            </div>

            <button
              className={`analyze-btn ${contractA && contractB && !serverConfig?.demo ? "ready" : "disabled"}`}
              onClick={() => runAnalysis(false)}
              disabled={!contractA || !contractB || !!serverConfig?.demo}
            >
              {contractA && contractB ? "Analyze Contracts →" : "Upload both contracts to continue"}
            </button>

            <div className="upload-footer-note">
              Contracts stay local — files are deleted after analysis. Every analysis is written to an append-only audit log (topics and counts only, never clause text).
            </div>
          </div>
        )}

        {/* ANALYZING PHASE */}
        {phase === "analyzing" && (
          <div className="analyzing-phase">
            <div className="analyzing-icon">
              <div className="analyzing-spinner" />
            </div>
            <h2>Analyzing contracts...</h2>
            <p>The agent is reading both contracts and identifying conflicts.</p>
            <ProgressBar steps={STEPS} currentStep={progressStep} message={progressMsg} />
            <ToolFeed tools={tools} />
          </div>
        )}

        {/* ERROR PHASE */}
        {phase === "error" && (
          <div className="error-phase">
            <div className="error-icon">!</div>
            <h2>Analysis failed</h2>
            <p>{errorMsg}</p>
            <button className="analyze-btn ready" onClick={reset}>Try Again</button>
          </div>
        )}

        {/* RESULTS PHASE */}
        {phase === "results" && report && (
          <div className="results-phase">
            <SummaryBar summary={report.summary} total={report.total_conflicts} />

            <div className="analysis-meta">
              {routeInfo && (
                <span className="meta-pill" title={routeInfo.reason}>
                  Strategy: <strong>{routeInfo.route === "agentic" ? "agentic loop" : "single pass"}</strong> ({routeInfo.source})
                </span>
              )}
              {report.governing_law && <span className="meta-pill">Governing law: <strong>{report.governing_law}</strong></span>}
              {judgeInfo && (
                <span className="meta-pill">Resolutions reviewed: <strong>{judgeInfo.reviewed}</strong>, flagged {judgeInfo.flagged}, withheld {judgeInfo.hidden}</span>
              )}
            </div>
            {notices.length > 0 && (
              <div className="notice-box">{notices.map((n, i) => <div key={i}>⚠ {n}</div>)}</div>
            )}

            {report.total_conflicts === 0 ? (
              <div className="no-conflicts">
                <div className="no-conflicts-icon">✓</div>
                <h3>No significant conflicts found</h3>
                <p>{report.recommendation}</p>
              </div>
            ) : (
              <>
                <div className="results-controls">
                  <FilterBar
                    active={filter}
                    onChange={setFilter}
                    counts={report.summary}
                  />
                  <div className="results-actions">
                    <div className="results-count">
                      Showing {filteredConflicts.length} of {report.total_conflicts} conflicts
                      <button className="link-btn" onClick={() => setExpandAll((v) => !v)}>{expandAll ? "Collapse all" : "Expand all"}</button>
                    </div>
                    <div className="download-buttons">
                      <button className="download-btn json" onClick={downloadJSON}>
                        ↓ JSON
                      </button>
                      <button className="download-btn pdf" onClick={downloadPDF} disabled={pdfLoading}>
                        {pdfLoading ? "Generating..." : "↓ PDF"}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="conflicts-list">
                  {filteredConflicts.map((conflict, i) => (
                    <ConflictCard key={`${conflict.id || i}-${expandAll}`} conflict={conflict} index={i} forceOpen={expandAll} />
                  ))}
                </div>

                {report.recommendation && (
                  <div className="recommendation-box">
                    <div className="rec-label">Recommendation</div>
                    <p>{report.recommendation}</p>
                  </div>
                )}
              </>
            )}

            {(traceInfo || report.trace) && (() => {
              const t = traceInfo || report.trace;
              return (
                <div className="trace-footer">
                  {demoRecordedAt && (
                    <span className="trace-replay-note">▶ Replayed trace recorded {new Date(demoRecordedAt).toISOString().slice(0, 10)}: the calls, cost and time below are from that recording; this session made no model calls.</span>
                  )}
                  {tools.length > 0 && <span>{tools.length} tool calls</span>}
                  <span>request {t.request_id}</span>
                  <span>{t.llm_calls} model calls</span>
                  <span>{(t.input_tokens || 0).toLocaleString()} in / {(t.output_tokens || 0).toLocaleString()} out</span>
                  <span>{(t.cache_read_tokens || 0).toLocaleString()} cached</span>
                  <span>${Number(t.cost_usd || 0).toFixed(3)}</span>
                  <span>{t.wall_time_s}s</span>
                </div>
              );
            })()}
          </div>
        )}
      </main>
    </div>
  );
}

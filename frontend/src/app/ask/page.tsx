"use client";

import { useState } from "react";
import { ApiRequestError, askReckoner, type AskResponse } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ERROR_COPY } from "@/components/Result";

type State = { kind: "idle" } | { kind: "loading" } | { kind: "error"; code: string; message: string } | { kind: "result"; r: AskResponse };

const EXAMPLES = ["Find me a tanky Duelist Lightning Strike build", "What changed for Lightning Strike in the latest PoE 2 patch?"];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [code, setCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (question.trim().length < 3) return;
    setState({ kind: "loading" });
    try {
      setState({ kind: "result", r: await askReckoner(question.trim(), undefined, code) });
    } catch (err) {
      if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
      else setState({ kind: "error", code: "unexpected", message: String(err) });
    }
  }

  const r = state.kind === "result" ? state.r : null;

  return (
    <main className="page">
      <Nav current="ask" />
      <form className="panel" onSubmit={onSubmit} aria-label="Ask">
        <label htmlFor="q" className="muted">
          Ask in your own words. The system searches, calculates and cites; the model only talks.
        </label>
        <textarea id="q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={EXAMPLES[0]} style={{ minHeight: 70 }} data-testid="ask-question" />
        <div className="row">
          <button type="submit" disabled={state.kind === "loading" || question.trim().length < 3} data-testid="ask-submit">
            {state.kind === "loading" ? "Thinking…" : "Ask"}
          </button>
          <button type="button" className="ghost" onClick={() => setShowCode((v) => !v)} data-testid="ask-toggle-code">
            {showCode ? "Hide build code" : "Attach a build code"}
          </button>
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" className="ghost" onClick={() => setQuestion(ex)}>
              {ex}
            </button>
          ))}
        </div>
        {showCode ? (
          <textarea value={code} onChange={(e) => setCode(e.target.value)} placeholder="eNrtfWtz3LbV…" style={{ marginTop: 8 }} data-testid="ask-code" aria-label="Build code" />
        ) : null}
        {state.kind === "error" ? (
          <p className="status error" role="alert" data-testid="error">
            {ERROR_COPY[state.code] ?? state.message} <span className="muted">[{state.code}]</span>
          </p>
        ) : null}
      </form>

      {r ? (
        <section className="panel fade" style={{ marginTop: 16 }} data-testid="ask-result" aria-live="polite">
          <pre className="answer" data-testid="ask-answer">
            {r.answer}
          </pre>

          <p className="prov" data-testid="ask-meta">
            orchestrated by <b className={r.model === "scripted" ? "estimated" : "calculated"}>{r.model}</b>
            {r.model === "scripted" ? " (no model — deterministic policy)" : ""} · {r.steps.length} tool call{r.steps.length === 1 ? "" : "s"} · {r.duration_ms} ms
            {r.input_tokens ? ` · ${r.input_tokens}+${r.output_tokens} tokens` : ""}
          </p>

          <p className={`prov audit ${r.audit.clean ? "ok" : "bad"}`} data-testid="ask-audit">
            {r.audit.clean
              ? `number audit: ${r.audit.checked} number${r.audit.checked === 1 ? "" : "s"} in the answer, all traceable to tool results`
              : `number audit: ${r.audit.unverified.length} of ${r.audit.checked} numbers match no tool result — treat as unverified: ${r.audit.unverified.join(", ")}`}
          </p>

          {r.degraded.length ? (
            <ul className="degraded" data-testid="ask-degraded">
              {r.degraded.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          ) : null}

          <details data-testid="ask-steps">
            <summary>How the answer was built ({r.steps.length} steps)</summary>
            <ol className="steps">
              {r.steps.map((s, i) => (
                <li key={i} className={s.ok ? "" : "bad"}>
                  <code>{s.tool}</code>({Object.entries(s.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}) → {s.ok ? s.summary : `refused: ${s.error}`}
                  <span className="muted"> · {s.duration_ms} ms</span>
                </li>
              ))}
            </ol>
          </details>

          {r.evidence.length ? (
            <details data-testid="ask-evidence">
              <summary>Evidence ({r.evidence.length})</summary>
              <ul className="evidence">
                {r.evidence.map((e, i) => (
                  <li key={i}>
                    {e.statement}
                    <span className="prov">
                      {" "}· <b className={e.provenance.status}>{e.provenance.status}</b>
                      {e.provenance.engine ? ` · ${e.provenance.engine}${e.provenance.engine_version ? " " + e.provenance.engine_version : ""}` : ` · ${e.provenance.source}`}
                      {e.provenance.game_version ? ` · patch ${e.provenance.game_version}` : ""}
                      {e.source_url ? (
                        <>
                          {" · "}
                          <a href={e.source_url} rel="noreferrer noopener" target="_blank">
                            source
                          </a>
                        </>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}

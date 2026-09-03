"use client";

import { useState } from "react";
import { ApiRequestError, askReckoner, type AskResponse } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ERROR_COPY } from "@/components/Result";

type State = { kind: "idle" } | { kind: "loading" } | { kind: "error"; code: string; message: string } | { kind: "result"; r: AskResponse };

const STEP_LABELS: Record<string, string> = {
  search_builds: "Searched builds",
  get_build: "Read a build",
  analyze_build_code: "Analysed the attached build",
  calculate_build: "Recalculated in the engine",
  compare_builds: "Compared builds",
  search_knowledge: "Searched patch notes",
  get_patch_changes: "Read patch notes",
  corpus_stats: "Checked how many builds are known",
  list_games: "Checked supported games",
};

function modelLabel(model: string): string {
  // "openai_compat:qwen2.5:7b@http://…" → "qwen2.5:7b (local)"; "anthropic:claude-…" → "claude-…"
  const m = model.replace(/^openai_compat:/, "").replace(/^anthropic:/, "");
  const [name, host] = m.split("@");
  if (host && /localhost|127\.0\.0\.1/.test(host)) return `${name} (local)`;
  return name;
}

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
          Ask in your own words. Reckoner searches its builds and patch notes, calculates, and cites where each number comes from.
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
            {r.model === "scripted" ? (
              <>
                <b className="estimated">offline mode</b> — no language model; answers are assembled deterministically
              </>
            ) : (
              <>
                written by <b className="calculated">{modelLabel(r.model)}</b>
              </>
            )}
            {" · "}
            {r.steps.length} step{r.steps.length === 1 ? "" : "s"} · {(r.duration_ms / 1000).toFixed(1)} s
          </p>

          <p className={`prov audit ${r.audit.clean ? "ok" : "bad"}`} data-testid="ask-audit">
            {r.audit.checked === 0
              ? "this answer contains no numbers"
              : r.audit.clean
                ? `${r.audit.checked} number${r.audit.checked === 1 ? "" : "s"} in this answer, every one produced by a calculation or a source`
                : `${r.audit.unverified.length} of ${r.audit.checked} numbers come from no calculation or source — treat as unverified: ${r.audit.unverified.join(", ")}`}
          </p>

          {r.steps.length > 0 && r.evidence.length === 0 ? (
            <p className="prov audit bad" data-testid="ask-no-evidence">
              nothing found to back this answer — no build and no source matched
            </p>
          ) : null}

          {r.degraded.length ? (
            <ul className="degraded" data-testid="ask-degraded">
              {r.degraded.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          ) : null}

          <details data-testid="ask-steps">
            <summary>How this answer was built ({r.steps.length} step{r.steps.length === 1 ? "" : "s"})</summary>
            <ol className="steps">
              {r.steps.map((s, i) => (
                <li key={i} className={s.ok ? "" : "bad"}>
                  {STEP_LABELS[s.tool] ?? s.tool}
                  {Object.keys(s.args).length ? (
                    <span className="muted mono"> {Object.entries(s.args).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ")}</span>
                  ) : null}
                  {" → "}
                  {s.ok ? s.summary : <span className="bad">could not: {s.error}</span>}
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
                    {e.statement.replace(/(\d)\.(\d)/g, "$1.$2")}
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

"use client";

import type { AskResponse } from "@/lib/api";

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
  const m = model.replace(/^openai_compat:/, "").replace(/^anthropic:/, "");
  const [name, host] = m.split("@");
  if (host && /localhost|127\.0\.0\.1/.test(host)) return `${name} (local)`;
  return name;
}

/** Everything that makes an answer checkable: who wrote it, the audit, the steps, the evidence. */
export function AnswerMeta({ r }: { r: AskResponse }) {
  return (
    <div className="answer-meta">
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
                <span className="muted mono">
                  {" "}
                  {Object.entries(s.args)
                    .filter(([, v]) => v !== null && v !== undefined)
                    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
                    .join(" · ")}
                </span>
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
                {e.statement}
                <span className="prov">
                  {" "}· <b className={e.provenance.status}>{e.provenance.status}</b>
                  {e.provenance.engine
                    ? ` · ${e.provenance.engine}${e.provenance.engine_version ? " " + e.provenance.engine_version : ""}`
                    : ` · ${e.provenance.source}`}
                  {e.provenance.game_version ? ` · patch ${e.provenance.game_version}` : ""}
                  {e.source_url && /^https?:\/\//.test(e.source_url) ? (
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
    </div>
  );
}

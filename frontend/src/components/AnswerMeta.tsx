"use client";

import type { AskResponse } from "@/lib/api";
import { provenanceLine } from "@/lib/copy";

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
            <b className="estimated">offline answer</b> — assembled from the data without an assistant
          </>
        ) : (
          <>
            answered with <b className="calculated">{modelLabel(r.model)}</b>
          </>
        )}
      </p>

      <p className={`prov audit ${r.audit.clean ? "ok" : "bad"}`} data-testid="ask-audit">
        {r.audit.checked === 0
          ? "no numbers in this answer"
          : r.audit.clean
            ? `✓ every number here comes from a calculation or a source`
            : `⚠ ${r.audit.unverified.length} number${r.audit.unverified.length === 1 ? "" : "s"} could not be verified: ${r.audit.unverified.join(", ")}`}
      </p>

      {r.steps.length > 0 && r.evidence.length === 0 ? (
        <p className="prov audit bad" data-testid="ask-no-evidence">
          nothing backs this answer — no build and no patch note matched
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
        <summary>How this was answered</summary>
        <ol className="steps">
          {r.steps.map((s, i) => (
            <li key={i} className={s.ok ? "" : "bad"}>
              {STEP_LABELS[s.tool] ?? s.tool}
              {" — "}
              {s.ok ? s.summary : <span className="bad">could not: {s.error}</span>}
            </li>
          ))}
        </ol>
      </details>

      {r.evidence.length ? (
        <details data-testid="ask-evidence">
          <summary>Sources ({r.evidence.length})</summary>
          <ul className="evidence">
            {r.evidence.map((e, i) => (
              <li key={i}>
                {e.statement}
                <span className="prov">
                  {" "}· <b className={e.provenance.status}>{provenanceLine(e.provenance).split(" ")[0]}</b>
                  {provenanceLine(e.provenance).slice(provenanceLine(e.provenance).split(" ")[0].length)}
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

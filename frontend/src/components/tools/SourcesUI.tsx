"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import type { Evidence } from "@/lib/api";
import { provenanceLine } from "@/lib/copy";

interface SourcesResult {
  evidence: Evidence[];
  audit: { checked: number; unverified: string[]; clean: boolean };
  degraded: string[];
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Where the numbers in the answer come from — collapsed by default, one honest line visible. */
export const SourcesUI = makeAssistantToolUI<Record<string, never>, SourcesResult>({
  toolName: "sources",
  render: ({ result }) => {
    if (!result) return null;
    const { evidence, audit, degraded } = result;
    const line =
      audit.checked === 0
        ? null
        : audit.clean
          ? "✓ numbers verified"
          : `⚠ ${audit.unverified.length} unverified number${audit.unverified.length === 1 ? "" : "s"}: ${audit.unverified.join(", ")}`;
    return (
      <details className="sources" data-testid="sources">
        <summary>
          {line ? (
            <span className={`audit ${audit.clean ? "ok" : "bad"}`} data-testid="ask-audit">
              {line}
            </span>
          ) : null}
          {evidence.length ? (
            <span className="muted"> · {evidence.length} source{evidence.length === 1 ? "" : "s"}</span>
          ) : (
            <span className="audit bad" data-testid="ask-no-evidence">
              {" "}· nothing found to back this
            </span>
          )}
          {degraded.map((d, i) => (
            <span key={i} className="audit bad" data-testid="ask-degraded">
              {" "}· {d.replace(/^[a-z_]+: /, "")}
            </span>
          ))}
        </summary>
        <ul className="evidence" data-testid="sources-list">
          {evidence.map((e, i) => (
            <li key={i}>
              <div>{e.statement}</div>
              <div className="prov">
                <b className={e.provenance.status}>{provenanceLine(e.provenance).split(" ")[0]}</b>
                {provenanceLine(e.provenance).slice(provenanceLine(e.provenance).split(" ")[0].length)}
                {e.source_url && /^https?:\/\//.test(e.source_url) ? (
                  <>
                    {" · "}
                    <a href={e.source_url} target="_blank" rel="noreferrer noopener">
                      {domainOf(e.source_url)}
                    </a>
                  </>
                ) : null}
              </div>
              {e.excerpt ? <blockquote className="excerpt">{e.excerpt}</blockquote> : null}
            </li>
          ))}
        </ul>
      </details>
    );
  },
});

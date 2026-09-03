"use client";

import { useAuiState } from "@assistant-ui/react";
import type { AskResponse, BuildSnapshot } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { usePanel } from "@/lib/panel";

export const CODE_RE = /e[JN][A-Za-z0-9+/_=-]{200,}/;

export interface ReckonerCustom {
  reckoner?: AskResponse;
  snapshot?: BuildSnapshot;
  code?: string;
  error?: { code: string; message: string };
}

function metric(s: BuildSnapshot, key: string): string {
  const m = s.metrics.find((x) => x.key === key);
  if (!m || m.value === null) return "—";
  return formatMetric(m.value, m.unit).short;
}

/** Under each answer: the build card handle (opens the panel) and one honesty line. Nothing technical. */
export function ReckonerExtras() {
  const custom = useAuiState((s) => s.message.metadata.custom) as ReckonerCustom | undefined;
  const open = usePanel((s) => s.open);
  if (!custom || custom.error) return null;
  const r = custom.reckoner;
  const s = custom.snapshot;
  return (
    <div className="reckoner-extras">
      {s ? (
        <button
          type="button"
          className="build-chip"
          onClick={() => open({ kind: "build", snapshot: s, code: custom.code })}
          data-testid="open-build"
        >
          <span className="build-chip-title">
            {s.character.class_name ?? "Build"}
            {s.character.subclass ? ` · ${s.character.subclass}` : ""}
            {s.main_skill ? ` · ${s.main_skill}` : ""}
          </span>
          <span className="build-chip-stats mono">
            DPS {metric(s, "dps.total")} · Life {metric(s, "life.max")} · EHP {metric(s, "ehp.total")}
          </span>
          <span className="build-chip-cta">View build →</span>
        </button>
      ) : null}
      {r ? (
        <div className="answer-foot" data-testid="answer-foot">
          {r.audit.checked > 0 ? (
            <span className={`audit ${r.audit.clean ? "ok" : "bad"}`} data-testid="ask-audit">
              {r.audit.clean ? "✓ numbers verified" : `⚠ ${r.audit.unverified.length} unverified number${r.audit.unverified.length === 1 ? "" : "s"}`}
            </span>
          ) : null}
          {r.evidence.length ? (
            <button
              type="button"
              className="foot-link"
              onClick={() => open({ kind: "sources", evidence: r.evidence, unverified: r.audit.unverified })}
              data-testid="open-sources"
            >
              {r.evidence.length} source{r.evidence.length === 1 ? "" : "s"}
            </button>
          ) : r.steps.length > 0 ? (
            <span className="audit bad" data-testid="ask-no-evidence">
              nothing found to back this
            </span>
          ) : null}
          {r.degraded.map((d, i) => (
            <span key={i} className="audit bad" data-testid="ask-degraded">
              {d.replace(/^[a-z_]+: /, "")}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** A pasted build code is 15 KB of base64: show what it is, not the blob. */
export function UserText({ text }: { text: string }) {
  const stripped = text.replace(CODE_RE, "").replace(/\s+/g, " ").trim();
  const hasCode = CODE_RE.test(text);
  return (
    <div className="msg-text" data-testid="ask-user-text">
      {stripped}
      {hasCode ? (
        <span className="chip" style={{ marginLeft: stripped ? 8 : 0 }} data-testid="ask-user-code">
          Path of Building code attached
        </span>
      ) : null}
    </div>
  );
}

"use client";

import { useState } from "react";
import {
  ApiRequestError,
  recalculateBuild,
  type BuildSnapshot,
  type BuildVariant,
  type Metric,
  type Modification,
  type SourceInfo,
} from "@/lib/api";
import { formatMetric, METRIC_LABELS, PRIMARY_METRICS } from "@/lib/format";
import { PassiveTree, type TreeDiff } from "@/components/tree/PassiveTree";
import { provenanceLine, unknownReason } from "@/lib/copy";

export const ERROR_COPY: Record<string, string> = {
  invalid_build_code: "This does not look like a build code we can read.",
  unsupported_game: "This game is not supported yet.",
  engine_unavailable: "The calculation engine is unavailable; no approximation is shown.",
  invalid_modification: "The engine refused this modification.",
  backend_unreachable: "The analysis service is unreachable.",
};

function ProvenanceLine({ m }: { m: Metric }) {
  if (!m.provenance) return <span className="prov">unknown — {unknownReason(m.unknown_reason)}</span>;
  const p = m.provenance;
  const aggregates = Array.isArray(p.context.aggregates) ? (p.context.aggregates as string[]) : [];
  return (
    <span className="prov" data-testid="provenance">
      <b className={p.status}>{provenanceLine(p).split(" ")[0]}</b>
      {provenanceLine(p).slice(provenanceLine(p).split(" ")[0].length)}
      {aggregates.length > 0 ? <span data-testid="aggregates"> · sums {aggregates.join(", ")}</span> : null}
    </span>
  );
}

function StatCard({ m }: { m: Metric }) {
  const label = METRIC_LABELS[m.key] ?? m.key;
  if (m.value === null) {
    return (
      <div className="stat" data-testid={`stat-${m.key}`} data-known="false">
        <div className="label">{label}</div>
        <div className="value unknown">unknown</div>
        <ProvenanceLine m={m} />
      </div>
    );
  }
  const f = formatMetric(m.value, m.unit);
  return (
    <div className="stat" data-testid={`stat-${m.key}`} data-known="true">
      <div className="label">{label}</div>
      <div className="value" title={f.long}>{f.short}</div>
      <ProvenanceLine m={m} />
    </div>
  );
}

type WhatIfState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; code: string; message: string }
  | { kind: "result"; variant: BuildVariant };

const BOSS_OPTIONS = ["None", "Boss", "Pinnacle", "Uber"];

function Delta({ before, after, unit, testId }: { before: number | null; after: number | null; unit: string | null; testId: string }) {
  if (before === null || after === null) return <span className="delta flat" data-testid={testId}>—</span>;
  const diff = after - before;
  const dir = Math.abs(diff) < 1e-9 ? "flat" : diff > 0 ? "up" : "down";
  const pct = before !== 0 ? ` (${diff > 0 ? "+" : "−"}${Math.abs((diff / before) * 100).toFixed(1)}%)` : "";
  const f = formatMetric(Math.abs(diff), unit).short;
  return (
    <span className={`delta ${dir}`} data-testid={testId}>
      {dir === "flat" ? "±0" : `${diff > 0 ? "+" : "−"}${f}${pct}`}
    </span>
  );
}

/** SPEC § 5 B — a modification is only ever evaluated by the real engine; the UI shows what it said. */
function diffTrees(v: BuildVariant): TreeDiff | null {
  if (!v.baseline) return null;
  const before = new Set(v.baseline.tree.node_ids);
  const after = new Set(v.snapshot.tree.node_ids);
  return {
    added: new Set([...after].filter((id) => !before.has(id))),
    removed: new Set([...before].filter((id) => !after.has(id))),
  };
}

function WhatIf({
  code,
  parent,
  request,
  onVariant,
}: {
  code: string;
  parent: BuildSnapshot;
  request?: (Modification & { seq: number }) | null;
  onVariant?: (v: BuildVariant | null) => void;
}) {
  const [kind, setKind] = useState("config.set");
  const [boss, setBoss] = useState("Uber");
  const [gem, setGem] = useState(parent.main_skill ?? "");
  const [level, setLevel] = useState("21");
  const [state, setState] = useState<WhatIfState>({ kind: "idle" });

  const [lastSeq, setLastSeq] = useState(0);

  function modification(): Modification | null {
    if (kind === "config.set") return { kind, payload: { name: "enemyIsBoss", value: boss } };
    if (kind === "gem.set_level") return gem ? { kind, payload: { gem, level: Number(level) } } : null;
    return null;
  }

  async function run(mod: Modification) {
    setState({ kind: "loading" });
    try {
      const variant = await recalculateBuild(code, [mod]);
      setState({ kind: "result", variant });
      onVariant?.(variant);
    } catch (err) {
      onVariant?.(null);
      if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
      else setState({ kind: "error", code: "unexpected", message: String(err) });
    }
  }

  // A click on the tree arrives as a request; run it once per click.
  if (request && request.seq !== lastSeq) {
    setLastSeq(request.seq);
    void run({ kind: request.kind, payload: request.payload });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const mod = modification();
    if (!mod) return;
    await run(mod);
  }

  const v = state.kind === "result" ? state.variant : null;
  const engineProv = v?.snapshot.metrics.find((m) => m.provenance)?.provenance ?? null;
  const applied = (engineProv?.context.modifications_applied as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <section className="whatif" aria-label="What if">
      <h2>Try a change</h2>
      <p className="hint">
        Click a passive on the tree above, or pick a change here. Everything is recalculated by Path of Building itself — the
        &quot;before&quot; column is this build re-evaluated by the same engine, so the comparison is fair.
      </p>
      <form onSubmit={onSubmit}>
        <select value={kind} onChange={(e) => setKind(e.target.value)} data-testid="mod-kind" aria-label="Change">
          <option value="config.set">Against which enemy?</option>
          <option value="gem.set_level">Main gem level</option>
        </select>
        {kind === "config.set" ? (
          <select value={boss} onChange={(e) => setBoss(e.target.value)} data-testid="mod-boss" aria-label="Enemy is boss">
            {BOSS_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : null}
        {kind === "gem.set_level" ? (
          <>
            <input value={gem} onChange={(e) => setGem(e.target.value)} placeholder="gem name" data-testid="mod-gem" aria-label="Gem" />
            <input value={level} onChange={(e) => setLevel(e.target.value)} inputMode="numeric" style={{ width: 64 }} data-testid="mod-level" aria-label="Level" />
          </>
        ) : null}
        <button type="submit" disabled={state.kind === "loading" || !modification()} data-testid="recalc">
          {state.kind === "loading" ? "Recalculating…" : "Recalculate"}
        </button>
        {state.kind === "error" ? (
          <span className="status error" data-testid="recalc-error" role="alert">
            {ERROR_COPY[state.code] ?? state.message}
            {ERROR_COPY[state.code] ? ` ${state.message}` : ""} <span className="muted">[{state.code}]</span>
          </span>
        ) : null}
      </form>

      {v && v.baseline ? (
        <div data-testid="whatif-result">
          <p className="prov" data-testid="engine-prov">
            <b className="calculated">calculated</b> by {engineProv?.engine} {engineProv?.engine_version} · game data {String(engineProv?.context.engine_data_version ?? "?")}
          </p>
          <p className="mono" data-testid="applied">
            changed:{" "}
            {applied.map((a, i) => (
              <span key={i}>
                {i > 0 ? "; " : ""}
                {String(a.kind)} {String(a.name ?? a.gem ?? "")}
                {a.value !== undefined ? ` → ${String(a.value)}` : a.level !== undefined ? ` → ${String(a.level)}` : ""}
              </span>
            ))}
            {" · "}
            <span data-testid="variant-nodes">{v.snapshot.tree.node_ids.length} passives</span>
          </p>
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th style={{ textAlign: "right" }}>In the export</th>
                <th style={{ textAlign: "right" }}>Before</th>
                <th style={{ textAlign: "right" }}>After</th>
                <th style={{ textAlign: "right" }}>Change</th>
              </tr>
            </thead>
            <tbody>
              {PRIMARY_METRICS.map((k) => {
                const exp = parent.metrics.find((m) => m.key === k);
                const base = v.baseline!.metrics.find((m) => m.key === k);
                const after = v.snapshot.metrics.find((m) => m.key === k);
                if (!base && !after) return null;
                const cell = (m: Metric | undefined) =>
                  m && m.value !== null ? formatMetric(m.value, m.unit).short : <span className="muted">unknown</span>;
                return (
                  <tr key={k} data-testid={`whatif-${k}`}>
                    <td>{METRIC_LABELS[k] ?? k}</td>
                    <td className="num">{cell(exp)}</td>
                    <td className="num">{cell(base)}</td>
                    <td className="num">{cell(after)}</td>
                    <td className="num">
                      <Delta before={base?.value ?? null} after={after?.value ?? null} unit={after?.unit ?? null} testId={`delta-${k}`} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export function Result({ snapshot: s, code, source }: { snapshot: BuildSnapshot; code?: string; source?: SourceInfo | null }) {
  const [treeDiff, setTreeDiff] = useState<TreeDiff | null>(null);
  const [treeRequest, setTreeRequest] = useState<(Modification & { seq: number }) | null>(null);
  const primary = PRIMARY_METRICS.map((k) => s.metrics.find((m) => m.key === k)).filter(Boolean) as Metric[];
  const rest = s.metrics.filter((m) => !PRIMARY_METRICS.includes(m.key));
  return (
    <section className="panel fade" data-testid="result" aria-live="polite">
      <div className="header-line">
        <span className="big" data-testid="character">
          {s.character.class_name ?? "?"}
          {s.character.subclass ? ` · ${s.character.subclass}` : ""}
        </span>
        <span className="mono muted">level {s.character.level ?? "?"}</span>
        <span
          className="mono"
          data-testid="main-skill"
          title="Socket group selected in the export — PoB's DPS figures are computed for this skill"
        >
          {s.main_skill ?? "main skill unknown"}
        </span>
        <span className="chip" data-testid="patch">patch {s.game_version ?? "unknown"}</span>
      </div>

      <div className="grid">
        {primary.map((m) => (
          <StatCard key={m.key} m={m} />
        ))}
      </div>

      <h2>Passive tree</h2>
      <p className="mono" data-testid="tree">
        {s.tree.unknown_reason
          ? `unknown — ${unknownReason(s.tree.unknown_reason)}`
          : `${s.tree.node_ids.length} passives · ${Object.keys(s.tree.mastery_effects).length} masteries · tree ${s.tree.version ?? "version unknown"}`}
      </p>
      {!s.tree.unknown_reason ? (
        <PassiveTree
          version={s.tree.version}
          allocated={s.tree.node_ids}
          ascendancy={s.character.subclass}
          diff={treeDiff ?? null}
          onNodeClick={code ? (id, allocated) => setTreeRequest({ kind: allocated ? "tree.deallocate" : "tree.allocate", payload: { node_id: id }, seq: Date.now() }) : undefined}
        />
      ) : null}
      {code ? <p className="hint">Click a passive to try the build without it, or with it. The result is recalculated by the real engine below.</p> : null}

      <h2>Details</h2>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th style={{ textAlign: "right" }}>Value</th>
            <th>Provenance</th>
          </tr>
        </thead>
        <tbody>
          {rest.map((m) => (
            <tr key={m.key} data-testid={`row-${m.key}`}>
              <td>{METRIC_LABELS[m.key] ?? m.key}</td>
              <td className="num">{m.value === null ? <span className="muted">—</span> : formatMetric(m.value, m.unit).short}</td>
              <td>
                <ProvenanceLine m={m} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Items ({s.items.length})</h2>
      <table data-testid="items">
        <thead>
          <tr>
            <th>Slot</th>
            <th>Item</th>
            <th>Rarity</th>
            <th style={{ textAlign: "right" }}>ilvl</th>
          </tr>
        </thead>
        <tbody>
          {s.items.map((it, i) => (
            <tr key={`${it.slot}-${i}`}>
              <td className="muted">{it.slot}</td>
              <td>
                {it.name ?? it.base_type}
                {it.name && it.base_type ? <span className="muted"> · {it.base_type}</span> : null}
              </td>
              <td className="mono muted">{it.rarity?.toLowerCase()}</td>
              <td className="num">{it.item_level ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Skill groups ({s.skills.length})</h2>
      <table data-testid="skills">
        <tbody>
          {s.skills.map((g, i) => (
            <tr key={i}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{g.slot ?? "—"}</td>
              <td className="mono">
                {g.gems.map((gem) => `${gem.name}${gem.level ? ` ${gem.level}` : ""}${gem.quality ? `/${gem.quality}` : ""}`).join(" · ")}
                {!g.enabled ? <span className="muted"> (disabled)</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {source ? (
        <p className="prov" data-testid="source">
          source ·{" "}
          {/^https?:\/\//.test(source.url) ? (
            <a href={source.url} rel="noreferrer noopener" target="_blank">
              {source.title ?? source.url}
            </a>
          ) : (
            <span>{source.title ?? source.url}</span>
          )}
          {source.parent_url ? (
            <>
              {" "}· from{" "}
              <a href={source.parent_url} rel="noreferrer noopener" target="_blank">
                {source.parent_url.replace(/^https?:\/\//, "")}
              </a>
            </>
          ) : null}

        </p>
      ) : null}
      {code ? (
        <WhatIf code={code} parent={s} request={treeRequest} onVariant={(v) => setTreeDiff(v ? diffTrees(v) : null)} />
      ) : (
        <p className="hint whatif" data-testid="whatif-unavailable">
          To try changes on this build, paste its code on the Analyse page — saved builds cannot be recalculated from here.
        </p>
      )}
    </section>
  );
}


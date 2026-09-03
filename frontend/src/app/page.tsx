"use client";

import { useState } from "react";
import {
  analyzeBuild,
  ApiRequestError,
  recalculateBuild,
  type BuildSnapshot,
  type BuildVariant,
  type Metric,
  type Modification,
} from "@/lib/api";
import { formatMetric, METRIC_LABELS, PRIMARY_METRICS } from "@/lib/format";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; code: string; message: string }
  | { kind: "result"; snapshot: BuildSnapshot };

const ERROR_COPY: Record<string, string> = {
  invalid_build_code: "This does not look like a build code we can read.",
  unsupported_game: "This game is not supported yet.",
  engine_unavailable: "The calculation engine is unavailable; no approximation is shown.",
  invalid_modification: "The engine refused this modification.",
  backend_unreachable: "The analysis service is unreachable.",
};

function ProvenanceLine({ m }: { m: Metric }) {
  if (!m.provenance) return <span className="prov">unknown — {m.unknown_reason}</span>;
  const p = m.provenance;
  return (
    <span className="prov" data-testid="provenance">
      <b className={p.status}>{p.status}</b>
      {p.engine ? <> · {p.engine}</> : null}
      {p.engine_version ? <> {p.engine_version}</> : p.engine ? <> (version not embedded)</> : null}
      {" · patch "}
      {p.game_version ?? "unknown"}
      {Array.isArray(p.context.aggregates) && p.context.aggregates.length > 0 ? (
        <span data-testid="aggregates"> · sums {(p.context.aggregates as string[]).join(", ")}</span>
      ) : null}
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
function WhatIf({ code, parent }: { code: string; parent: BuildSnapshot }) {
  const [kind, setKind] = useState("tree.deallocate");
  const [node, setNode] = useState("");
  const [boss, setBoss] = useState("Uber");
  const [gem, setGem] = useState(parent.main_skill ?? "");
  const [level, setLevel] = useState("21");
  const [state, setState] = useState<WhatIfState>({ kind: "idle" });

  function modification(): Modification | null {
    if (kind === "tree.deallocate" || kind === "tree.allocate") {
      const id = Number(node);
      return Number.isInteger(id) ? { kind, payload: { node_id: id } } : null;
    }
    if (kind === "config.set") return { kind, payload: { name: "enemyIsBoss", value: boss } };
    if (kind === "gem.set_level") return gem ? { kind, payload: { gem, level: Number(level) } } : null;
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const mod = modification();
    if (!mod) return;
    setState({ kind: "loading" });
    try {
      setState({ kind: "result", variant: await recalculateBuild(code, [mod]) });
    } catch (err) {
      if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
      else setState({ kind: "error", code: "unexpected", message: String(err) });
    }
  }

  const v = state.kind === "result" ? state.variant : null;
  const engineProv = v?.snapshot.metrics.find((m) => m.provenance)?.provenance ?? null;
  const applied = (engineProv?.context.modifications_applied as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <section className="whatif" aria-label="What if">
      <h2>What if</h2>
      <p className="hint">
        Changes are applied inside headless Path of Building and recalculated there. Baseline = this export re-evaluated by the same
        engine; the export column is what the author&apos;s PoB wrote.
      </p>
      <form onSubmit={onSubmit}>
        <select value={kind} onChange={(e) => setKind(e.target.value)} data-testid="mod-kind" aria-label="Modification">
          <option value="tree.deallocate">Deallocate passive node</option>
          <option value="tree.allocate">Allocate passive node</option>
          <option value="config.set">Enemy is boss</option>
          <option value="gem.set_level">Main gem level</option>
        </select>
        {kind === "tree.deallocate" || kind === "tree.allocate" ? (
          <input value={node} onChange={(e) => setNode(e.target.value)} placeholder="node id, e.g. 41119" inputMode="numeric" data-testid="mod-node" aria-label="Node id" />
        ) : null}
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
            <b className="calculated">calculated</b> · {engineProv?.engine} {engineProv?.engine_version} · source {engineProv?.source} · data{" "}
            {String(engineProv?.context.engine_data_version ?? "?")}
            {engineProv?.context.engine_source_commit ? ` · commit ${String(engineProv.context.engine_source_commit).slice(0, 8)}` : ""}
          </p>
          <p className="mono" data-testid="applied">
            applied:{" "}
            {applied.map((a, i) => (
              <span key={i}>
                {i > 0 ? "; " : ""}
                {String(a.kind)} {String(a.name ?? a.gem ?? "")}
                {a.value !== undefined ? ` → ${String(a.value)}` : a.level !== undefined ? ` → ${String(a.level)}` : ""}
              </span>
            ))}
            {" · "}
            <span data-testid="variant-nodes">{v.snapshot.tree.node_ids.length} nodes</span>
          </p>
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th style={{ textAlign: "right" }}>Export</th>
                <th style={{ textAlign: "right" }}>Baseline (engine)</th>
                <th style={{ textAlign: "right" }}>Variant</th>
                <th style={{ textAlign: "right" }}>Δ vs baseline</th>
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

function Result({ snapshot: s, code }: { snapshot: BuildSnapshot; code: string }) {
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
        <span className="chip">{s.game}</span>
        <span className="chip" title={s.raw.sha256}>input sha256 {s.raw.sha256.slice(0, 10)}…</span>
      </div>

      <div className="grid">
        {primary.map((m) => (
          <StatCard key={m.key} m={m} />
        ))}
      </div>

      <h2>All metrics</h2>
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
              <td className="num">{m.value === null ? <span className="muted">unknown</span> : formatMetric(m.value, m.unit).short}</td>
              <td>
                <ProvenanceLine m={m} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Passive tree</h2>
      <p className="mono" data-testid="tree">
        {s.tree.unknown_reason
          ? `unknown — ${s.tree.unknown_reason}`
          : `${s.tree.node_ids.length} allocated nodes · tree ${s.tree.version ?? "version unknown"} · ${Object.keys(s.tree.mastery_effects).length} masteries`}
      </p>

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

      <WhatIf code={code} parent={s} />
    </section>
  );
}

export default function Home() {
  const [code, setCode] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setState({ kind: "loading" });
    try {
      const snapshot = await analyzeBuild(code);
      setState({ kind: "result", snapshot });
    } catch (err) {
      if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
      else setState({ kind: "error", code: "unexpected", message: String(err) });
    }
  }

  return (
    <main className="page">
      <header className="topbar">
        <h1>Reckoner</h1>
        <span className="mono muted">phase 1 · analyse an existing build</span>
      </header>

      <form className="panel" onSubmit={onSubmit} aria-label="Analyze a build">
        <label htmlFor="code" className="muted">
          Paste a Path of Building export code
        </label>
        <textarea
          id="code"
          name="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          spellCheck={false}
          placeholder="eNrtfWtz3LbV…"
          data-testid="code-input"
        />
        <div className="row">
          <button type="submit" disabled={state.kind === "loading" || !code.trim()} data-testid="analyze">
            {state.kind === "loading" ? "Analyzing…" : "Analyze"}
          </button>
          {state.kind === "loading" ? (
            <span className="status" data-testid="status" role="status">
              reading export…
            </span>
          ) : null}
          {state.kind === "error" ? (
            <span className="status error" data-testid="error" role="alert">
              {ERROR_COPY[state.code] ?? state.message} <span className="muted">[{state.code}]</span>
            </span>
          ) : null}
        </div>
      </form>

      {state.kind === "result" ? (
        <div style={{ marginTop: 16 }}>
          <Result snapshot={state.snapshot} code={code} />
        </div>
      ) : null}
    </main>
  );
}

"use client";

import { useState } from "react";
import { analyzeBuild, ApiRequestError, type BuildSnapshot, type Metric } from "@/lib/api";
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

function Result({ snapshot: s }: { snapshot: BuildSnapshot }) {
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
          <Result snapshot={state.snapshot} />
        </div>
      ) : null}
    </main>
  );
}

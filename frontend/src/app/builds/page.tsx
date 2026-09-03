"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiRequestError, searchBuilds, type BuildSummary, type Metric } from "@/lib/api";
import { formatMetric } from "@/lib/format";
import { Nav } from "@/components/Nav";
import { ERROR_COPY } from "@/components/Result";

const isWebUrl = (u: string | null | undefined) => !!u && /^https?:\/\//.test(u);

const CLASSES = ["", "Duelist", "Marauder", "Ranger", "Scion", "Shadow", "Templar", "Witch"];

type State =
  | { kind: "loading" }
  | { kind: "error"; code: string; message: string }
  | { kind: "result"; total: number; items: BuildSummary[] };

function Cell({ m }: { m: Metric | undefined }) {
  if (!m) return <td className="num muted">—</td>;
  if (m.value === null)
    return (
      <td className="num muted" title={`unknown — ${m.unknown_reason ?? ""}`}>
        unknown
      </td>
    );
  const p = m.provenance!;
  return (
    <td className="num" title={`${p.status} · ${p.engine ?? p.source}${p.engine_version ? " " + p.engine_version : ""} · patch ${p.game_version ?? "unknown"}`}>
      {formatMetric(m.value, m.unit).short}
    </td>
  );
}

export default function BuildsPage() {
  const [className, setClassName] = useState("");
  const [skill, setSkill] = useState("");
  const [minDps, setMinDps] = useState("");
  const [applied, setApplied] = useState({ className: "", skill: "", minDps: "" });
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    searchBuilds({
      game: "poe",
      class_name: applied.className || undefined,
      main_skill: applied.skill || undefined,
      min_dps: applied.minDps ? Number(applied.minDps) : undefined,
      limit: 50,
    })
      .then((r) => !cancelled && setState({ kind: "result", total: r.total, items: r.items }))
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
        else setState({ kind: "error", code: "unexpected", message: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [applied]);

  const metric = (b: BuildSummary, key: string) => b.metrics.find((m) => m.key === key);

  return (
    <main className="page">
      <Nav current="builds" />
      <section className="panel">
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            setState({ kind: "loading" });
            setApplied({ className, skill, minDps });
          }}
          aria-label="Filter builds"
        >
          <select value={className} onChange={(e) => setClassName(e.target.value)} data-testid="filter-class" aria-label="Class">
            {CLASSES.map((c) => (
              <option key={c} value={c}>
                {c || "any class"}
              </option>
            ))}
          </select>
          <input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="main skill contains…" data-testid="filter-skill" aria-label="Main skill" />
          <input value={minDps} onChange={(e) => setMinDps(e.target.value)} placeholder="min DPS" inputMode="numeric" style={{ width: 110 }} data-testid="filter-min-dps" aria-label="Minimum DPS" />
          <button type="submit" data-testid="filter-apply">
            Filter
          </button>
          {state.kind === "result" ? (
            <span className="mono muted" data-testid="total">
              {state.total} build{state.total === 1 ? "" : "s"}
            </span>
          ) : null}
        </form>

        {state.kind === "error" ? (
          <p className="status error" role="alert" data-testid="error">
            {ERROR_COPY[state.code] ?? state.message} <span className="muted">[{state.code}]</span>
          </p>
        ) : null}

        {state.kind === "result" && state.items.length === 0 ? (
          <p className="mono muted" data-testid="corpus-empty">
            No build matches. The corpus only contains what was ingested from permitted sources; it is not padded.
          </p>
        ) : null}

        {state.kind === "result" && state.items.length > 0 ? (
          <table data-testid="builds-table">
            <thead>
              <tr>
                <th>Character</th>
                <th>Main skill</th>
                <th>Patch</th>
                <th style={{ textAlign: "right" }}>DPS</th>
                <th style={{ textAlign: "right" }}>Life</th>
                <th style={{ textAlign: "right" }}>EHP</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {state.items.map((b) => (
                <tr key={b.snapshot_id} data-testid="build-row">
                  <td>
                    <Link href={`/builds/${b.snapshot_id}`} data-testid="build-link">
                      {b.character.class_name ?? "?"}
                      {b.character.subclass ? ` · ${b.character.subclass}` : ""}
                    </Link>
                    <span className="muted mono"> lvl {b.character.level ?? "?"}</span>
                  </td>
                  <td>{b.main_skill ?? <span className="muted">unknown</span>}</td>
                  <td className="mono muted">{b.game_version ?? "unknown"}</td>
                  <Cell m={metric(b, "dps.total")} />
                  <Cell m={metric(b, "life.max")} />
                  <Cell m={metric(b, "ehp.total")} />
                  <td className="muted">
                    {b.source ? (
                      isWebUrl(b.source.parent_url ?? b.source.url) ? (
                        <a href={b.source.parent_url ?? b.source.url} rel="noreferrer noopener" target="_blank" title={b.source.terms ?? ""}>
                          {b.source.title ?? b.source.kind}
                        </a>
                      ) : (
                        <span title={b.source.terms ?? ""}>{b.source.title ?? b.source.kind}</span>
                      )
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { getTalentGeometry, type TalentGeometry, type TalentTable } from "@/lib/api";

const CELL = 40;
const R = 13;

type GridTree = TalentGeometry["trees"][number];

/** Without the engine's grid, the chosen talents alone still have a place: their own row/column. */
function fromTables(tables: TalentTable[]): GridTree[] {
  return tables.map((t) => ({
    kind: t.kind,
    subtree: null,
    rows: Math.max(0, ...t.talents.map((x) => x.row)),
    columns: t.columns,
    nodes: t.talents.map((x) => ({ node: x.spell_id, row: x.row, col: x.col, max_rank: x.rank, choices: [{ name: x.name, spell_id: x.spell_id }] })),
  }));
}

/**
 * World of Warcraft talents: class, specialisation and hero trees as a grid. Positions come from
 * SimulationCraft's talent data; the taken talents from its decoding of the build's loadout string.
 * Display only — a loadout cannot be re-encoded here, so nothing is clickable.
 */
export function TalentGrid({ game, className, spec, tables }: { game: string; className: string | null; spec: string | null; tables: TalentTable[] }) {
  const [geo, setGeo] = useState<TalentGeometry | null>(null);
  useEffect(() => {
    if (!className || !spec) return;
    let alive = true;
    getTalentGeometry(game, className, spec)
      .then((g) => alive && setGeo(g))
      .catch(() => alive && setGeo(null));
    return () => {
      alive = false;
    };
  }, [game, className, spec]);

  const taken = new Map<number, { name: string; rank: number }>();
  for (const t of tables) for (const x of t.talents) taken.set(x.spell_id, { name: x.name, rank: x.rank });
  const titles = new Map<string, TalentTable>();
  for (const t of tables) titles.set(t.kind === "hero" ? `hero:${t.talents[0]?.spell_id ?? ""}` : t.kind, t);

  const trees: GridTree[] = geo
    ? // Only the hero tree the build actually took is shown; the other one is not in the build.
      geo.trees.filter((t) => t.kind !== "hero" || t.nodes.some((n) => n.choices.some((c) => taken.has(c.spell_id))))
    : fromTables(tables);

  return (
    <div className="talent-grid" data-testid="talent-grid" data-source={geo ? "engine-grid" : "build-only"}>
      {trees.map((tree, i) => {
        const table =
          tree.kind === "hero"
            ? tables.find((t) => t.kind === "hero" && t.talents.some((x) => tree.nodes.some((n) => n.choices.some((c) => c.spell_id === x.spell_id))))
            : tables.find((t) => t.kind === tree.kind);
        const label = table ? `${table.title} talents` : tree.kind === "hero" ? "Hero talents" : `${tree.kind} talents`;
        return (
          <figure className="talent-tree" key={`${tree.kind}-${tree.subtree ?? i}`} data-testid={`talent-tree-${tree.kind}`}>
            <figcaption>
              <span>{label}</span>
              {table ? <span className="muted"> · {table.points} points</span> : null}
            </figcaption>
            <svg width={tree.columns * CELL} height={tree.rows * CELL} viewBox={`0 0 ${tree.columns * CELL} ${tree.rows * CELL}`} role="img" aria-label={label}>
              {tree.nodes.map((n) => {
                const chosen = n.choices.find((c) => taken.has(c.spell_id));
                const got = chosen ? taken.get(chosen.spell_id) : undefined;
                const cx = (n.col - 0.5) * CELL;
                const cy = (n.row - 0.5) * CELL;
                const tip = chosen && got ? `${chosen.name} · ${got.rank}/${n.max_rank}` : n.choices.map((c) => c.name).join(" or ") + " · not taken";
                return (
                  <g key={n.node}>
                    <circle
                      className={`tnode${chosen ? " taken" : ""}${n.choices.length > 1 ? " choice" : ""}`}
                      cx={cx}
                      cy={cy}
                      r={R}
                      data-spell-id={chosen?.spell_id ?? n.choices[0]?.spell_id}
                      data-taken={chosen ? "true" : "false"}
                    >
                      <title>{tip}</title>
                    </circle>
                    {chosen && got && n.max_rank > 1 ? (
                      <text x={cx} y={cy + 4} textAnchor="middle" className="trank">
                        {got.rank}/{n.max_rank}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>
          </figure>
        );
      })}
    </div>
  );
}

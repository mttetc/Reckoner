"use client";

import { useEffect, useMemo, useState } from "react";
import { API_URL, getTreeGeometry, type TreeGeometry } from "@/lib/api";

/**
 * The whole passive tree, faint, behind the conversation. Drawn from the same engine geometry as
 * the build cards — no copyrighted artwork, just the shape every Path of Exile player knows.
 * Purely decorative: no pointer events, hidden from assistive tech, static under reduced motion.
 */
export function TreeBackdrop() {
  const [geo, setGeo] = useState<TreeGeometry | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/v1/games`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((games: Array<{ id: string; latest_tree_version: string | null }>) => {
        const version = games.find((g) => g.id === "poe")?.latest_tree_version;
        if (!version) return null;
        return getTreeGeometry("poe", version);
      })
      .then((g) => {
        if (!cancelled && g) setGeo(g);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const model = useMemo(() => {
    if (!geo) return null;
    // Main tree only: no ascendancies, no masteries, and none of the cluster-jewel templates
    // that sit outside the graph without neighbours.
    const nodes = geo.nodes.filter((n) => !n.ascendancy && n.type !== "Mastery" && n.linked.length > 0);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y);
    }
    const seen = new Set<string>();
    const lines: string[] = [];
    for (const n of nodes) {
      for (const other of n.linked) {
        const m = byId.get(other);
        if (!m) continue;
        const key = n.id < other ? `${n.id}-${other}` : `${other}-${n.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        lines.push(`M${n.x} ${n.y}L${m.x} ${m.y}`);
      }
    }
    return { nodes, path: lines.join(""), box: `${minX - 400} ${minY - 400} ${maxX - minX + 800} ${maxY - minY + 800}` };
  }, [geo]);

  if (!model) return null;
  return (
    <div className="tree-backdrop" aria-hidden="true" data-testid="tree-backdrop">
      <svg viewBox={model.box} preserveAspectRatio="xMidYMid slice">
        <path d={model.path} className="backdrop-edges" />
        {model.nodes.map((n) => (
          <circle
            key={n.id}
            cx={n.x}
            cy={n.y}
            r={n.type === "Keystone" ? 80 : n.type === "Notable" ? 52 : n.type === "ClassStart" ? 110 : 30}
            className={`backdrop-node ${n.type}`}
          />
        ))}
      </svg>
    </div>
  );
}

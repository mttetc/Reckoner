"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError, getTreeGeometry, type TreeGeometry, type TreeNode } from "@/lib/api";

/**
 * Passive tree drawn from the geometry the game engine computes (Path of Building), not from a
 * re-implementation. Allocated nodes and their connectors are lit; a what-if diff shows removed
 * nodes in red and added ones in green. Cluster-jewel nodes live only inside a build's own graph,
 * so they are counted, not drawn — and the count is shown.
 */

export interface TreeDiff {
  added: Set<number>;
  removed: Set<number>;
}

const RADIUS: Record<string, number> = {
  Normal: 26,
  Notable: 40,
  Keystone: 56,
  Mastery: 34,
  Socket: 40,
  ClassStart: 64,
  AscendClassStart: 44,
};

function nodeRadius(n: TreeNode): number {
  return (RADIUS[n.type] ?? 26) * (n.ascendancy ? 0.8 : 1);
}

function arcPath(a: TreeNode, b: TreeNode, geo: TreeGeometry): string | null {
  // Same group and orbit: draw the orbit arc like the game does; otherwise a straight line.
  if (a.g == null || a.o == null || a.g !== b.g || a.o !== b.o || a.angle == null || b.angle == null) return null;
  const r = geo.orbit_radii[a.o];
  if (!r) return null;
  let delta = b.angle - a.angle;
  while (delta <= -Math.PI) delta += Math.PI * 2;
  while (delta > Math.PI) delta -= Math.PI * 2;
  const sweep = delta > 0 ? 1 : 0;
  return `M ${a.x} ${a.y} A ${r} ${r} 0 0 ${sweep} ${b.x} ${b.y}`;
}

export function PassiveTree({
  version,
  allocated,
  ascendancy,
  diff,
  height = 560,
}: {
  version: string | null;
  allocated: number[];
  ascendancy?: string | null;
  diff?: TreeDiff | null;
  height?: number;
}) {
  const [geo, setGeo] = useState<TreeGeometry | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [hover, setHover] = useState<TreeNode | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!version) return;
    let cancelled = false;
    getTreeGeometry("poe", version)
      .then((g) => !cancelled && setGeo(g))
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiRequestError) setError({ code: e.body.code, message: e.body.message });
        else setError({ code: "unexpected", message: String(e) });
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const alloc = useMemo(() => new Set(allocated), [allocated]);
  const clusterCount = useMemo(() => allocated.filter((id) => id >= 65536).length, [allocated]);

  const model = useMemo(() => {
    if (!geo) return null;
    const byId = new Map(geo.nodes.map((n) => [n.id, n]));
    // Hide other classes' ascendancies; keep the build's own (or all when none is known).
    const visible = geo.nodes.filter((n) => !n.ascendancy || !ascendancy || n.ascendancy === ascendancy);
    const visibleIds = new Set(visible.map((n) => n.id));
    const edges: Array<{ key: string; d: string; lit: boolean; state: "on" | "off" | "added" | "removed" }> = [];
    const seen = new Set<string>();
    for (const n of visible) {
      for (const other of n.linked) {
        if (!visibleIds.has(other)) continue;
        const key = n.id < other ? `${n.id}-${other}` : `${other}-${n.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const m = byId.get(other)!;
        if (n.type === "Mastery" || m.type === "Mastery") continue;
        const d = arcPath(n, m, geo) ?? `M ${n.x} ${n.y} L ${m.x} ${m.y}`;
        const both = alloc.has(n.id) && alloc.has(m.id);
        let state: "on" | "off" | "added" | "removed" = both ? "on" : "off";
        if (diff) {
          if (diff.removed.has(n.id) || diff.removed.has(m.id)) state = both ? "removed" : state;
          if (diff.added.has(n.id) || diff.added.has(m.id)) state = "added";
        }
        edges.push({ key, d, lit: both, state });
      }
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of visible) {
      minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y);
    }
    const pad = 300;
    return { visible, edges, bounds: { x: minX - pad, y: minY - pad, w: maxX - minX + pad * 2, h: maxY - minY + pad * 2 } };
  }, [geo, ascendancy, alloc, diff]);

  // viewBox pan/zoom (wheel + drag), no dependency. `override` is null until the user moves.
  const [override, setView] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const view = override ?? model?.bounds ?? null;
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function onWheel(e: React.WheelEvent<SVGSVGElement>) {
    if (!view || !svgRef.current) return;
    e.preventDefault();
    const rect = svgRef.current.getBoundingClientRect();
    const px = view.x + ((e.clientX - rect.left) / rect.width) * view.w;
    const py = view.y + ((e.clientY - rect.top) / rect.height) * view.h;
    const k = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const w = Math.min(Math.max(view.w * k, 600), (model?.bounds.w ?? view.w) * 2);
    const h = (w * view.h) / view.w;
    setView({ x: px - ((px - view.x) / view.w) * w, y: py - ((py - view.y) / view.h) * h, w, h });
  }
  function onPointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (!view) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    setDragging(true);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }
  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!drag.current || !view || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((e.clientX - drag.current.x) / rect.width) * view.w;
    const dy = ((e.clientY - drag.current.y) / rect.height) * view.h;
    setView({ ...view, x: drag.current.vx - dx, y: drag.current.vy - dy });
  }
  function onPointerUp() {
    drag.current = null;
    setDragging(false);
  }

  if (!version) return <p className="state" data-testid="tree-unavailable">Tree version unknown for this export — nothing to draw.</p>;
  if (error)
    return (
      <p className="state" data-testid="tree-unavailable">
        {error.code === "engine_unavailable" ? "Tree rendering needs the calculation engine, which is not installed here." : error.message}{" "}
        <span className="muted">[{error.code}]</span>
      </p>
    );
  if (!model || !view) return <p className="state" data-testid="tree-loading">loading tree geometry…</p>;

  const total = allocated.length;
  return (
    <div className="tree" data-testid="tree-view">
      <div className="tree-bar">
        <span className="mono">
          <b>{total - clusterCount}</b> allocated nodes drawn · tree {version.replace("_", ".")}
          {clusterCount ? ` · ${clusterCount} cluster-jewel nodes not drawn (they exist only inside this build)` : ""}
        </span>
        {diff ? (
          <span className="mono">
            <span className="added">+{diff.added.size}</span> <span className="removed">−{diff.removed.size}</span> vs baseline
          </span>
        ) : null}
        <button type="button" className="ghost" onClick={() => setView(null)} data-testid="tree-reset">
          fit
        </button>
      </div>
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        style={{ width: "100%", height, touchAction: "none", cursor: dragging ? "grabbing" : "grab" }}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        role="img"
        aria-label={`Passive tree, ${total} allocated nodes`}
      >
        <g className="edges">
          {model.edges.map((e) => (
            <path key={e.key} d={e.d} className={`edge ${e.state}`} />
          ))}
        </g>
        <g className="nodes">
          {model.visible.map((n) => {
            const on = alloc.has(n.id);
            const state = diff?.removed.has(n.id) ? "removed" : diff?.added.has(n.id) ? "added" : on ? "on" : "off";
            return (
              <circle
                key={n.id}
                cx={n.x}
                cy={n.y}
                r={nodeRadius(n)}
                className={`node ${n.type} ${state}`}
                data-node-id={n.id}
                data-allocated={on ? "true" : "false"}
                onPointerEnter={() => setHover(n)}
                onPointerLeave={() => setHover(null)}
              >
                <title>{`${n.name || n.type}${n.ascendancy ? ` · ${n.ascendancy}` : ""}${on ? " · allocated" : ""}`}</title>
              </circle>
            );
          })}
        </g>
      </svg>
      <div className="tree-hover mono" data-testid="tree-hover" aria-live="polite">
        {hover ? `${hover.name || hover.type} · ${hover.type}${hover.ascendancy ? ` · ${hover.ascendancy}` : ""}${alloc.has(hover.id) ? " · allocated" : ""} · #${hover.id}` : "hover a node"}
      </div>
    </div>
  );
}

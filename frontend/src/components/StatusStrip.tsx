"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { gameName } from "@/lib/copy";

interface Status {
  engine: boolean | null;
  builds: number | null;
  patches: Record<string, number> | null;
  chunks: number | null;
}

/** Live facts about what this instance can do — the honesty strip. Fails quietly to "unknown". */
export function StatusStrip() {
  const [s, setS] = useState<Status>({ engine: null, builds: null, patches: null, chunks: null });
  useEffect(() => {
    let cancelled = false;
    const j = (p: string) => fetch(`${API_URL}${p}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([j("/api/v1/games"), j("/api/v1/corpus/stats"), j("/api/v1/knowledge/stats")]).then(([games, corpus, knowledge]) => {
      if (cancelled) return;
      const poe = Array.isArray(games) ? games.find((g: { id: string }) => g.id === "poe") : null;
      setS({
        engine: poe ? Boolean(poe.capabilities?.recalculate_modified) : null,
        builds: corpus ? corpus.snapshots : null,
        patches: knowledge ? knowledge.per_game : null,
        chunks: knowledge ? knowledge.chunks : null,
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <div className="strip" data-testid="status-strip" aria-label="Instance status">
      <span>
        <span className={`dot ${s.engine === null ? "" : s.engine ? "ok" : "off"}`} />
        {s.engine === null ? "checking the calculator…" : s.engine ? <b>live recalculation available</b> : <b>recalculation unavailable on this server</b>}
      </span>
      <span>{s.builds === null ? "" : <b>{s.builds} builds indexed</b>}</span>
      <span>
        {s.patches ? (
          <b>
            patch notes for {Object.keys(s.patches).map((g) => gameName(g)).join(" and ")}
          </b>
        ) : (
          ""
        )}
      </span>
    </div>
  );
}

"use client";

import { useState } from "react";
import { ApiRequestError, searchKnowledge, type KnowledgeHit } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ERROR_COPY } from "@/components/Result";

function staleNote(retrievedAt: string | null): React.ReactNode {
  if (!retrievedAt) return null;
  const days = Math.floor((Date.now() - new Date(retrievedAt).getTime()) / 86_400_000);
  if (days < 30) return null;
  return (
    <span className="estimated" data-testid="stale">
      {" "}· retrieved {days} days ago, may be stale
    </span>
  );
}

const GAMES: Array<{ id: string; label: string }> = [
  { id: "poe", label: "Path of Exile" },
  { id: "poe2", label: "Path of Exile 2" },
];

type State = { kind: "idle" } | { kind: "loading" } | { kind: "error"; code: string; message: string } | { kind: "result"; hits: KnowledgeHit[]; game: string };

export default function KnowledgePage() {
  const [game, setGame] = useState("poe");
  const [q, setQ] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setState({ kind: "loading" });
    try {
      setState({ kind: "result", hits: await searchKnowledge(game, q.trim(), 8), game });
    } catch (err) {
      if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
      else setState({ kind: "error", code: "unexpected", message: String(err) });
    }
  }

  return (
    <main className="page">
      <Nav current="knowledge" />
      <section className="panel">
        <p className="hint">
          Official patch notes, split by section and tagged with their patch. Results are always limited to the game you pick: PoE and
          PoE 2 share names, not mechanics, so a passage from the other game is never a valid answer.
        </p>
        <form className="filters" onSubmit={onSubmit} aria-label="Search knowledge">
          <select value={game} onChange={(e) => setGame(e.target.value)} data-testid="kn-game" aria-label="Game">
            {GAMES.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Lightning Strike changes" style={{ minWidth: 280 }} data-testid="kn-query" aria-label="Question" />
          <button type="submit" disabled={state.kind === "loading" || q.trim().length < 2} data-testid="kn-search">
            {state.kind === "loading" ? "Searching…" : "Search"}
          </button>
        </form>

        {state.kind === "error" ? (
          <p className="status error" role="alert" data-testid="error">
            {ERROR_COPY[state.code] ?? state.message} <span className="muted">[{state.code}]</span>
          </p>
        ) : null}

        {state.kind === "result" && state.hits.length === 0 ? (
          <p className="mono muted" data-testid="kn-empty">
            Nothing in the {state.game} knowledge base matches. Nothing was borrowed from the other game.
          </p>
        ) : null}

        {state.kind === "result" && state.hits.length > 0 ? (
          <ol className="hits" data-testid="kn-results">
            {state.hits.map((h) => (
              <li key={h.chunk.id} className="hit" data-testid="kn-hit" data-game={h.chunk.metadata.game}>
                <div className="prov">
                  <b className="calculated">{h.chunk.metadata.game}</b>
                  {h.chunk.metadata.patch ? <> · patch {h.chunk.metadata.patch}</> : null}
                  {h.chunk.metadata.version ? <> ({h.chunk.metadata.version})</> : null}
                  {" · "}
                  {h.chunk.metadata.source_url ? (
                    <a href={h.chunk.metadata.source_url} rel="noreferrer noopener" target="_blank">
                      {h.title ?? h.chunk.metadata.source}
                    </a>
                  ) : (
                    h.title ?? h.chunk.metadata.source
                  )}
                  {h.heading ? <> › {h.heading}</> : null}
                  {h.chunk.metadata.published_at ? <> · published {h.chunk.metadata.published_at.slice(0, 10)}</> : null}
                  <span className="muted"> · relevance {Math.round(h.score * 100)}%</span>
                  {staleNote(h.chunk.metadata.retrieved_at)}
                </div>
                <pre className="excerpt">{h.chunk.text}</pre>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </main>
  );
}

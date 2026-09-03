"use client";

import { useState } from "react";
import { analyzeBuild, ApiRequestError, type BuildSnapshot } from "@/lib/api";
import { ERROR_COPY, Result } from "@/components/Result";
import { Nav } from "@/components/Nav";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; code: string; message: string }
  | { kind: "result"; snapshot: BuildSnapshot };

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
      <Nav current="analyze" />

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

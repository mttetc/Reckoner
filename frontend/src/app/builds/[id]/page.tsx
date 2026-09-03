"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiRequestError, getBuild, type BuildDetail } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ERROR_COPY, Result } from "@/components/Result";

type State = { kind: "loading" } | { kind: "error"; code: string; message: string } | { kind: "result"; detail: BuildDetail };

export default function BuildPage() {
  const params = useParams<{ id: string }>();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    getBuild(params.id)
      .then((detail) => setState({ kind: "result", detail }))
      .catch((err) => {
        if (err instanceof ApiRequestError) setState({ kind: "error", code: err.body.code, message: err.body.message });
        else setState({ kind: "error", code: "unexpected", message: String(err) });
      });
  }, [params.id]);

  return (
    <main className="page">
      <Nav current="builds" />
      {state.kind === "loading" ? <p className="mono muted">loading…</p> : null}
      {state.kind === "error" ? (
        <p className="status error" role="alert" data-testid="error">
          {ERROR_COPY[state.code] ?? state.message} <span className="muted">[{state.code}]</span>
        </p>
      ) : null}
      {state.kind === "result" ? <Result snapshot={state.detail.snapshot} source={state.detail.source} /> : null}
    </main>
  );
}

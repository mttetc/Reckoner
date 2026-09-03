"use client";

import { useState } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { ApiRequestError, askReckoner, type AskResponse } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ERROR_COPY } from "@/components/Result";
import { AnswerMeta } from "@/components/AnswerMeta";

const EXAMPLES = [
  "Find me a tanky Duelist Lightning Strike build",
  "What changed for Lightning Strike in the latest PoE 2 patch?",
  "Which Witch builds have the most effective HP?",
];

// The build code attached to the conversation. Read by the adapter at send time; never sent to
// the model itself — the backend tools read it (see ADR-011 field notes).
let attachedCode = "";

const adapter: ChatModelAdapter = {
  async run({ messages, abortSignal }) {
    const last = [...messages].reverse().find((m) => m.role === "user");
    const question = last
      ? last.content
          .filter((c) => c.type === "text")
          .map((c) => (c as { text: string }).text)
          .join("\n")
      : "";
    try {
      const r = await askReckoner(question, undefined, attachedCode || undefined);
      if (abortSignal.aborted) return { content: [] };
      return {
        content: [{ type: "text", text: r.answer || "(no answer text)" }],
        metadata: { custom: { reckoner: r } },
      };
    } catch (err) {
      const code = err instanceof ApiRequestError ? err.body.code : "unexpected";
      const message = err instanceof ApiRequestError ? err.body.message : String(err);
      return {
        content: [{ type: "text", text: `${ERROR_COPY[code] ?? message} [${code}]` }],
        metadata: { custom: { error: { code, message } } },
      };
    }
  },
};

function UserMessage() {
  return (
    <MessagePrimitive.Root className="msg user" data-testid="ask-user">
      <MessagePrimitive.Parts components={{ Text: ({ text }) => <div className="msg-text">{text}</div> }} />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const custom = useAuiState((s) => s.message.metadata.custom) as { reckoner?: AskResponse; error?: { code: string } } | undefined;
  const isError = Boolean(custom?.error);
  return (
    <MessagePrimitive.Root className="msg assistant" data-testid="ask-result">
      <MessagePrimitive.Parts
        components={{
          Text: ({ text }) => (
            <div className={`msg-text ${isError ? "status error" : ""}`} data-testid={isError ? "error" : "ask-answer"} role={isError ? "alert" : undefined}>
              {text}
            </div>
          ),
        }}
      />
      {custom?.reckoner ? <AnswerMeta r={custom.reckoner} /> : null}
    </MessagePrimitive.Root>
  );
}

function Running() {
  const running = useAuiState((s) => s.thread.isRunning);
  return running ? (
    <p className="thinking" data-testid="ask-thinking">
      searching, calculating, citing
    </p>
  ) : null;
}

function Composer() {
  const [showCode, setShowCode] = useState(false);
  const [code, setCode] = useState("");
  return (
    <>
      {showCode ? (
        <textarea
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            attachedCode = e.target.value;
          }}
          placeholder="Paste a Path of Building code — the tools read it, the model never sees the blob"
          aria-label="Build code"
          data-testid="ask-code"
          style={{ marginBottom: 8 }}
        />
      ) : null}
      <ComposerPrimitive.Root className="composer">
        <ComposerPrimitive.Input placeholder={EXAMPLES[0]} aria-label="Question" data-testid="ask-question" autoFocus />
        <button type="button" className="ghost" onClick={() => setShowCode((v) => !v)} data-testid="ask-toggle-code">
          {showCode ? "Hide code" : attachedCode ? "Code attached" : "Attach a build code"}
        </button>
        <ComposerPrimitive.Send data-testid="ask-submit">Ask</ComposerPrimitive.Send>
      </ComposerPrimitive.Root>
    </>
  );
}

function Suggestions() {
  return (
    <div className="suggestions">
      {EXAMPLES.map((ex) => (
        <ThreadPrimitive.Suggestion key={ex} prompt={ex} send asChild>
          <button type="button" className="ghost">
            {ex}
          </button>
        </ThreadPrimitive.Suggestion>
      ))}
    </div>
  );
}

export default function AskPage() {
  const runtime = useLocalRuntime(adapter);
  return (
    <main className="page">
      <Nav current="ask" />
      <AssistantRuntimeProvider runtime={runtime}>
        <section className="panel">
          <ThreadPrimitive.Root className="thread">
            <ThreadPrimitive.Viewport className="thread-viewport">
              <ThreadPrimitive.Empty>
                <p className="hint" style={{ marginTop: 0 }}>
                  Ask in your own words. Reckoner searches its builds and patch notes, calculates, and cites where each number comes
                  from. Nothing is estimated; when it does not know, it says so.
                </p>
                <Suggestions />
              </ThreadPrimitive.Empty>
              <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
              <Running />
            </ThreadPrimitive.Viewport>
            <Composer />
          </ThreadPrimitive.Root>
        </section>
      </AssistantRuntimeProvider>
    </main>
  );
}

"use client";

import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  WebSpeechDictationAdapter,
  WebSpeechSynthesisAdapter,
  useLocalRuntime,
  type ChatModelAdapter,
  type FeedbackAdapter,
  type SuggestionAdapter,
  type ThreadAssistantMessagePart,
} from "@assistant-ui/react";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { EXAMPLE_PROMPTS, Thread } from "@/components/assistant-ui/elements/thread.aui";
import { ThreadListSidebar } from "@/components/assistant-ui/elements/threadlist-sidebar.aui";
import { BuildCardUI } from "@/components/tools/BuildCardUI";
import { SourcesUI } from "@/components/tools/SourcesUI";
import { StepUIs } from "@/components/tools/StepUI";
import { ERROR_COPY } from "@/components/Result";
import { CODE_RE } from "@/components/UserText";
import { API_URL, analyzeBuild, ApiRequestError, type AskResponse } from "@/lib/api";

type StepEvent =
  | { type: "step_start"; id: string; tool: string; args: Record<string, string | number | boolean | null> }
  | { type: "step_end"; id: string; tool: string; ok: boolean; summary: string; error: string | null }
  | { type: "done"; response: AskResponse }
  | { type: "error"; message: string };

/** Reads the backend's server-sent events one JSON object at a time. */
async function* sse(res: Response, signal: AbortSignal): AsyncGenerator<StepEvent> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) yield JSON.parse(line.slice(6)) as StepEvent;
    }
  }
}

/** Everything behind one streaming adapter: live steps, then the answer, the build and the sources. */
const adapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    const last = [...messages].reverse().find((m) => m.role === "user");
    const raw = last
      ? last.content
          .filter((c) => c.type === "text")
          .map((c) => (c as { text: string }).text)
          .join("\n")
      : "";
    // A pasted Path of Building code travels to the tools, never to the model.
    const code = raw.match(CODE_RE)?.[0];
    const question = raw.replace(CODE_RE, "").trim() || (code ? "Analyse this build" : raw);

    const snapshotPromise = code ? analyzeBuild(code).catch(() => undefined) : Promise.resolve(undefined);
    const steps: ThreadAssistantMessagePart[] = [];
    let res: Response;
    try {
      res = await fetch(`${API_URL}/api/v1/ask/stream`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, game: null, code: code ?? null }),
        signal: abortSignal,
      });
    } catch {
      yield { content: [{ type: "text", text: ERROR_COPY.backend_unreachable }] };
      return;
    }
    if (!res.ok || !res.body) {
      let message = ERROR_COPY.http_error ?? `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.code) message = ERROR_COPY[body.code] ?? body.message ?? message;
      } catch {
        /* keep default */
      }
      yield { content: [{ type: "text", text: message }] };
      return;
    }

    let answer: AskResponse | undefined;
    for await (const ev of sse(res, abortSignal)) {
      if (ev.type === "step_start") {
        steps.push({ type: "tool-call", toolCallId: ev.id, toolName: ev.tool, args: ev.args, argsText: JSON.stringify(ev.args) });
        yield { content: [...steps] };
      } else if (ev.type === "step_end") {
        const i = steps.findIndex((p) => p.type === "tool-call" && p.toolCallId === ev.id);
        if (i >= 0) steps[i] = { ...(steps[i] as Extract<ThreadAssistantMessagePart, { type: "tool-call" }>), result: { ok: ev.ok, summary: ev.summary, error: ev.error } };
        yield { content: [...steps] };
      } else if (ev.type === "done") {
        answer = ev.response;
      } else if (ev.type === "error") {
        yield { content: [...steps, { type: "text", text: ev.message }] };
        return;
      }
    }
    if (!answer) {
      yield { content: [...steps, { type: "text", text: "The answer did not arrive." }] };
      return;
    }
    const snapshot = await snapshotPromise;
    const content: ThreadAssistantMessagePart[] = [...steps, { type: "text", text: answer.answer || "(no answer text)" }];
    if (snapshot) {
      content.push({ type: "tool-call", toolCallId: `build-${snapshot.id}`, toolName: "build_card", args: {}, argsText: "{}", result: { snapshot, code } });
    }
    content.push({
      type: "tool-call",
      toolCallId: `sources-${Date.now()}`,
      toolName: "sources",
      args: {},
      argsText: "{}",
      result: { evidence: answer.evidence, audit: answer.audit, degraded: answer.degraded },
    });
    yield { content, metadata: { custom: { suggestions: answer.suggestions } } };
  },
};

/** Follow-ups come from what the tools actually returned; the empty thread gets the examples. */
const suggestion: SuggestionAdapter = {
  async generate({ messages }) {
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    const fromAnswer = (lastAssistant?.metadata?.custom as { suggestions?: string[] } | undefined)?.suggestions;
    const prompts = messages.length === 0 ? EXAMPLE_PROMPTS : (fromAnswer ?? []);
    return prompts.map((prompt) => ({ prompt }));
  },
};

const feedback: FeedbackAdapter = {
  submit: ({ message, type }) => {
    const text = message.content
      .filter((c) => c.type === "text")
      .map((c) => (c as { text: string }).text)
      .join("\n");
    void fetch(`${API_URL}/api/v1/feedback`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message_id: message.id, rating: type, answer: text.slice(0, 8000) }),
    }).catch(() => undefined);
  },
};

export default function Home() {
  const runtime = useLocalRuntime(adapter, {
    adapters: {
      attachments: new CompositeAttachmentAdapter([new SimpleTextAttachmentAdapter()]),
      feedback,
      suggestion,
      speech: new WebSpeechSynthesisAdapter(),
      dictation: new WebSpeechDictationAdapter(),
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <BuildCardUI />
      <SourcesUI />
      <StepUIs />
      <SidebarProvider>
        <ThreadListSidebar />
        <SidebarInset>
          <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
            <SidebarTrigger data-testid="sidebar-trigger" />
            <span className="font-mono text-xs tracking-[0.18em] uppercase">Reckoner</span>
          </header>
          <div className="h-[calc(100dvh-3rem)]">
            <Thread />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
}

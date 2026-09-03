"use client";

import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadAssistantMessagePart,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { BuildCardUI } from "@/components/tools/BuildCardUI";
import { SourcesUI } from "@/components/tools/SourcesUI";
import { ERROR_COPY } from "@/components/Result";
import { CODE_RE } from "@/components/UserText";
import { analyzeBuild, ApiRequestError, askReckoner } from "@/lib/api";

/** The whole backend behind one adapter: the answer as text, the build and the sources as tool UIs. */
const adapter: ChatModelAdapter = {
  async run({ messages, abortSignal }) {
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
    try {
      const [answer, snapshot] = await Promise.all([
        askReckoner(question, undefined, code),
        code ? analyzeBuild(code).catch(() => undefined) : Promise.resolve(undefined),
      ]);
      if (abortSignal.aborted) return { content: [] };
      const content: ThreadAssistantMessagePart[] = [{ type: "text", text: answer.answer || "(no answer text)" }];
      if (snapshot) {
        content.push({
          type: "tool-call",
          toolCallId: `build-${snapshot.id}`,
          toolName: "build_card",
          args: {},
          argsText: "{}",
          result: { snapshot, code },
        });
      }
      content.push({
        type: "tool-call",
        toolCallId: `sources-${Date.now()}`,
        toolName: "sources",
        args: {},
        argsText: "{}",
        result: { evidence: answer.evidence, audit: answer.audit, degraded: answer.degraded },
      });
      return { content };
    } catch (err) {
      const errCode = err instanceof ApiRequestError ? err.body.code : "unexpected";
      const message = err instanceof ApiRequestError ? err.body.message : String(err);
      return { content: [{ type: "text", text: ERROR_COPY[errCode] ?? message }] };
    }
  },
};

export default function Home() {
  const runtime = useLocalRuntime(adapter, {
    adapters: { attachments: new CompositeAttachmentAdapter([new SimpleTextAttachmentAdapter()]) },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <BuildCardUI />
      <SourcesUI />
      <div className="h-dvh">
        <Thread />
      </div>
    </AssistantRuntimeProvider>
  );
}

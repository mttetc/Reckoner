"use client";

import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { SidePanel } from "@/components/SidePanel";
import { ERROR_COPY } from "@/components/Result";
import { CODE_RE, type ReckonerCustom } from "@/components/ReckonerExtras";
import { analyzeBuild, ApiRequestError, askReckoner } from "@/lib/api";
import { usePanel } from "@/lib/panel";

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
      const custom: ReckonerCustom = { reckoner: answer, snapshot, code };
      return {
        content: [{ type: "text", text: answer.answer || "(no answer text)" }],
        metadata: { custom: custom as Record<string, unknown> },
      };
    } catch (err) {
      const errCode = err instanceof ApiRequestError ? err.body.code : "unexpected";
      const message = err instanceof ApiRequestError ? err.body.message : String(err);
      const custom: ReckonerCustom = { error: { code: errCode, message } };
      return {
        content: [{ type: "text", text: ERROR_COPY[errCode] ?? message }],
        metadata: { custom: custom as Record<string, unknown> },
      };
    }
  },
};

export default function Home() {
  const runtime = useLocalRuntime(adapter, {
    adapters: { attachments: new CompositeAttachmentAdapter([new SimpleTextAttachmentAdapter()]) },
  });
  const panelOpen = usePanel((s) => s.content !== null);
  const openPanel = usePanel((s) => s.open);

  // Links in answers open on the right, like a reading pane; the site can still be opened in a tab.
  function onClickCapture(e: React.MouseEvent) {
    const a = (e.target as HTMLElement).closest?.("a[href^='http']") as HTMLAnchorElement | null;
    if (!a || a.closest(".side-panel")) return;
    e.preventDefault();
    openPanel({ kind: "link", url: a.href, title: a.textContent?.trim() || undefined });
  }

  return (
    <div className={`shell ${panelOpen ? "with-panel" : ""}`}>
      <header className="shell-head">
        <span className="wordmark">
          Reck<span>o</span>ner
        </span>
      </header>
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="shell-body">
          <div className="chat-frame" onClickCapture={onClickCapture}>
            <Thread />
          </div>
          <SidePanel />
        </div>
      </AssistantRuntimeProvider>
    </div>
  );
}

"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import type { BuildSnapshot } from "@/lib/api";
import { Result } from "@/components/Result";

/** The one thing assistant-ui cannot know about: a build, its numbers, its tree and what-if.
 *  Rendered inside the answer through assistant-ui's tool UI mechanism. */
export const BuildCardUI = makeAssistantToolUI<Record<string, never>, { snapshot: BuildSnapshot; code?: string }>({
  toolName: "build_card",
  render: ({ result }) => {
    if (!result) return null;
    return (
      <div className="in-chat-card" data-testid="build-card">
        <Result snapshot={result.snapshot} code={result.code} compact />
      </div>
    );
  },
});

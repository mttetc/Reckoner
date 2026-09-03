"use client";

import type { ExportedMessageRepositoryItem, RemoteThreadListAdapter, ThreadHistoryAdapter, ThreadMessage } from "@assistant-ui/react";
import { createAssistantStream } from "assistant-stream";
import { API_URL } from "@/lib/api";

/** Conversations live in PostgreSQL behind /api/v1/threads; assistant-ui drives them through these two adapters. */

interface ThreadView {
  id: string;
  title: string | null;
  status: "regular" | "archived";
  created_at: string;
  last_message_at: string | null;
}

interface MessageView {
  id: string;
  parent_id: string | null;
  message: Record<string, unknown>;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} → HTTP ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Dates travel as ISO strings; assistant-ui expects Date objects back. */
function revive(message: Record<string, unknown>): ThreadMessage {
  const m = { ...message } as Record<string, unknown>;
  if (typeof m.createdAt === "string") m.createdAt = new Date(m.createdAt);
  return m as unknown as ThreadMessage;
}

/**
 * History for the current thread. A brand-new thread has no server id until its first message is
 * sent, so writes initialise it on demand (the canonical shape of assistant-ui's cloud adapter).
 */
export const threadHistory = (
  currentId: () => string | undefined,
  ensureId: () => Promise<string>,
): ThreadHistoryAdapter => ({
  async load() {
    const threadId = currentId();
    if (!threadId) return { headId: null, messages: [] };
    const items = await api<MessageView[]>(`/threads/${threadId}/messages`);
    const messages: ExportedMessageRepositoryItem[] = items.map((it) => ({ message: revive(it.message), parentId: it.parent_id }));
    return { headId: messages.at(-1)?.message.id ?? null, messages };
  },
  async append({ message, parentId }) {
    const threadId = await ensureId();
    await api(`/threads/${threadId}/messages`, { method: "POST", body: JSON.stringify({ message, parent_id: parentId }) });
  },
  async update({ message, parentId }) {
    const threadId = await ensureId();
    await api(`/threads/${threadId}/messages`, { method: "POST", body: JSON.stringify({ message, parent_id: parentId }) });
  },
});

const toMeta = (t: ThreadView) => ({
  remoteId: t.id,
  status: t.status,
  title: t.title ?? undefined,
  lastMessageAt: t.last_message_at ? new Date(t.last_message_at) : undefined,
});

export function makeThreadListAdapter(Provider: RemoteThreadListAdapter["unstable_Provider"]): RemoteThreadListAdapter {
  return {
    async list() {
      const threads = await api<ThreadView[]>("/threads");
      return { threads: threads.map(toMeta) };
    },
    async initialize() {
      const t = await api<ThreadView>("/threads", { method: "POST" });
      return { remoteId: t.id };
    },
    async fetch(threadId) {
      return toMeta(await api<ThreadView>(`/threads/${threadId}`));
    },
    async rename(remoteId, newTitle) {
      await api(`/threads/${remoteId}`, { method: "PATCH", body: JSON.stringify({ title: newTitle }) });
    },
    async archive(remoteId) {
      await api(`/threads/${remoteId}`, { method: "PATCH", body: JSON.stringify({ status: "archived" }) });
    },
    async unarchive(remoteId) {
      await api(`/threads/${remoteId}`, { method: "PATCH", body: JSON.stringify({ status: "regular" }) });
    },
    async delete(remoteId) {
      await api(`/threads/${remoteId}`, { method: "DELETE" });
    },
    async generateTitle(remoteId) {
      // The server names a thread from its first question; stream that name back.
      const t = await api<ThreadView>(`/threads/${remoteId}`);
      return createAssistantStream((c: { appendText: (text: string) => void }) => {
        c.appendText(t.title ?? "New conversation");
      });
    },
    unstable_Provider: Provider,
  };
}

"use client";

import { create } from "zustand";
import type { BuildSnapshot, Evidence } from "@/lib/api";

/** What the right-hand panel shows, ChatGPT-style: a build in full, the sources of an answer, or a link. */
export type PanelContent =
  | { kind: "build"; snapshot: BuildSnapshot; code?: string }
  | { kind: "sources"; evidence: Evidence[]; unverified: string[] }
  | { kind: "link"; url: string; title?: string };

interface PanelState {
  content: PanelContent | null;
  open: (content: PanelContent) => void;
  close: () => void;
}

export const usePanel = create<PanelState>((set) => ({
  content: null,
  open: (content) => set({ content }),
  close: () => set({ content: null }),
}));

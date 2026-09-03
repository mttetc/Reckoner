"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { Loader2Icon, CheckIcon, XIcon } from "lucide-react";

/** One line per thing Reckoner does while answering — live, in the player's words. */
const LABELS: Record<string, [running: string, done: string]> = {
  search_builds: ["Searching builds", "Searched builds"],
  get_build: ["Reading a build", "Read a build"],
  analyze_build_code: ["Reading your build", "Read your build"],
  calculate_build: ["Recalculating in the engine", "Recalculated in the engine"],
  compare_builds: ["Comparing builds", "Compared builds"],
  search_knowledge: ["Searching patch notes", "Searched patch notes"],
  get_patch_changes: ["Reading patch notes", "Read patch notes"],
  corpus_stats: ["Checking what is known", "Checked what is known"],
  list_games: ["Checking supported games", "Checked supported games"],
};

interface StepResult {
  ok: boolean;
  summary: string;
  error: string | null;
}

function makeStepUI(toolName: string) {
  const [running, done] = LABELS[toolName] ?? [toolName, toolName];
  return makeAssistantToolUI<Record<string, unknown>, StepResult>({
    toolName,
    render: ({ result, status }) => {
      const isRunning = status.type === "running" || !result;
      return (
        <div className="step-line" data-testid="step" data-tool={toolName} data-state={isRunning ? "running" : result.ok ? "ok" : "error"}>
          {isRunning ? <Loader2Icon className="step-icon spin" size={12} /> : result.ok ? <CheckIcon className="step-icon" size={12} /> : <XIcon className="step-icon" size={12} />}
          <span>{isRunning ? `${running}…` : `${done}${result.summary ? ` — ${result.summary}` : ""}${!result.ok && result.error ? ` — ${result.error}` : ""}`}</span>
        </div>
      );
    },
  });
}

const STEP_UIS = Object.keys(LABELS).map(makeStepUI);

/** Mount once inside the runtime provider. */
export function StepUIs() {
  return (
    <>
      {STEP_UIS.map((Ui, i) => (
        <Ui key={i} />
      ))}
    </>
  );
}

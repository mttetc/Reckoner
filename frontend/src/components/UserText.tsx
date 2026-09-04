"use client";

export const CODE_RE = /e[JN][A-Za-z0-9+/_=-]{200,}/;
/** The first line of a SimulationCraft addon profile: `<class>="<name>"`. */
const SIMC_CLASS_LINE_RE = /(?:^|\s)((?:deathknight|demonhunter|druid|evoker|hunter|mage|monk|paladin|priest|rogue|shaman|warlock|warrior)="[^"\n]*")/;
/** Lines a profile is made of: comments, blanks, `key=value` / `key+=value` overrides. */
const SIMC_LINE_RE = /^\s*(?:#.*|[A-Za-z_][\w.]*\s*\+?=.*|)$/;

/** The profile runs from its class line to the last line that still looks like profile text. */
export function extractSimcProfile(text: string): string | null {
  const start = text.match(SIMC_CLASS_LINE_RE);
  if (!start || start.index === undefined) return null;
  const from = start.index + start[0].indexOf(start[1]);
  const lines = text.slice(from).split("\n");
  let end = 1;
  while (end < lines.length && SIMC_LINE_RE.test(lines[end])) end++;
  const payload = lines.slice(0, end).join("\n").trim();
  return /\bspec=\w+/.test(payload) ? payload : null;
}
/** A WoWSims exporter payload: one JSON object with a class. */
const WOWSIMS_RE = /\{[\s\S]*"class"\s*:\s*"[^"]+"[\s\S]*\}/;

export interface BuildPayload {
  payload: string;
  label: string;
}

/** Finds a build payload the backend can read inside what the user typed. The backend decides the game. */
export function extractBuildPayload(text: string): BuildPayload | null {
  const pob = text.match(CODE_RE);
  if (pob) return { payload: pob[0], label: "Path of Building code attached" };
  const simc = extractSimcProfile(text);
  if (simc) return { payload: simc, label: "SimulationCraft profile attached" };
  const sims = text.match(WOWSIMS_RE);
  if (sims) {
    try {
      JSON.parse(sims[0]);
      return { payload: sims[0], label: "WoWSims export attached" };
    } catch {
      /* not JSON after all */
    }
  }
  return null;
}

/** A pasted payload is thousands of characters: show what it is, not the blob. */
export function UserText({ text }: { text: string }) {
  const found = extractBuildPayload(text);
  const stripped = (found ? text.replace(found.payload, "") : text).replace(/\s+/g, " ").trim();
  return (
    <div data-testid="ask-user-text">
      {stripped}
      {found ? (
        <span className="chip" style={{ marginLeft: stripped ? 8 : 0 }} data-testid="ask-user-code">
          {found.label}
        </span>
      ) : null}
    </div>
  );
}

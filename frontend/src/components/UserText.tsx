"use client";

export const CODE_RE = /e[JN][A-Za-z0-9+/_=-]{200,}/;
/** A SimulationCraft addon profile: a class line followed by key=value lines. */
const SIMC_RE = /(?:^|\n)(?:deathknight|demonhunter|druid|evoker|hunter|mage|monk|paladin|priest|rogue|shaman|warlock|warrior)="[^"\n]*"\n[\s\S]*?\bspec=\w+[\s\S]*?(?=\n\s*\n(?![#a-z_0-9]+=)|$)/;
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
  const simc = text.match(SIMC_RE);
  if (simc) return { payload: simc[0].trim(), label: "SimulationCraft profile attached" };
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

// Player-facing wording. Internal identifiers never reach the screen.

export const GAME_NAMES: Record<string, string> = {
  poe: "Path of Exile",
  poe2: "Path of Exile 2",
  diablo3: "Diablo III",
  wow: "World of Warcraft",
  wow_classic: "World of Warcraft Classic",
};
export const gameName = (id: string | null | undefined) => (id ? GAME_NAMES[id] ?? id : "");

export const STATUS_WORDS: Record<string, string> = {
  calculated: "calculated",
  observed: "observed",
  estimated: "estimated",
  claimed: "stated by the source",
};

/** "engine reported a non-finite value for 'TotalEHP' (inf/nan)" → "could not be computed" */
export function unknownReason(reason: string | null | undefined): string {
  if (!reason) return "unknown";
  if (/not present in this export/i.test(reason)) return "not in this export";
  if (/non-finite/i.test(reason)) return "could not be computed for this setup";
  if (/no allocated nodes/i.test(reason)) return "no passive tree in this export";
  if (/unsupported encoding/i.test(reason)) return "tree format not readable";
  return reason.replace(/'[A-Za-z]+'/g, "").replace(/\s+/g, " ").trim();
}

/** One line that says where a number comes from, in words a player reads at a glance. */
export function provenanceLine(p: { status: string; engine: string | null; engine_version: string | null; source: string; game_version: string | null }): string {
  const who = p.engine ? `${STATUS_WORDS[p.status] ?? p.status} by ${p.engine}${p.engine_version ? " " + p.engine_version : ""}` : `${STATUS_WORDS[p.status] ?? p.status} · ${sourceName(p.source)}`;
  return p.game_version ? `${who} · patch ${p.game_version}` : who;
}

export function sourceName(source: string): string {
  if (source.startsWith("ggg:")) return "official patch notes";
  if (source.startsWith("simc:")) return "SimulationCraft";
  if (source.startsWith("wowsims:")) return "WoWSims";
  if (source === "pob:export") return "the build's export";
  if (source === "pob:headless") return "recalculation";
  return source;
}

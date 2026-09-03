const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });

export function formatMetric(value: number, unit: string | null): { short: string; long: string } {
  if (unit === "%") return { short: `${full.format(value)}%`, long: `${full.format(value)}%` };
  if (unit === "x") return { short: `×${full.format(value)}`, long: `×${value}` };
  if (unit === "/s") return { short: `${full.format(value)}/s`, long: `${value}/s` };
  const short = Math.abs(value) >= 10_000 ? compact.format(value) : full.format(value);
  return { short, long: full.format(value) };
}

export const METRIC_LABELS: Record<string, string> = {
  "dps.total": "DPS",
  "dps.combined": "Combined DPS",
  "dps.full": "Full DPS",
  "life.max": "Life",
  "life.unreserved": "Life (unreserved)",
  "energy_shield.max": "Energy shield",
  "ehp.total": "Effective HP",
  "mana.max": "Mana",
  "mana.unreserved": "Mana (unreserved)",
  "defence.armour": "Armour",
  "defence.evasion": "Evasion",
  "defence.block_chance": "Block",
  "defence.spell_block_chance": "Spell block",
  "defence.physical_damage_reduction": "Phys. reduction",
  "resist.fire": "Fire res.",
  "resist.cold": "Cold res.",
  "resist.lightning": "Lightning res.",
  "resist.chaos": "Chaos res.",
  "offence.speed": "Speed",
  "offence.crit_chance": "Crit chance",
  "offence.crit_multiplier": "Crit multi",
  "utility.movement_speed_mod": "Move speed",
  "minion.dps.total": "Minion DPS",
  "minion.life.max": "Minion life",
};

// dps.full is the sum of the groups the author flagged for Full DPS; it is often the number a
// guide quotes when dps.total belongs to a utility skill left selected in the export.
export const PRIMARY_METRICS = [
  "dps.total",
  "dps.full",
  "minion.dps.total",
  "life.max",
  "energy_shield.max",
  "ehp.total",
];

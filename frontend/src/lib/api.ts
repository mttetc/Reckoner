// Thin client for the Reckoner backend. Types mirror app/domain (backend/app/domain/*.py).

export type ProvenanceStatus = "observed" | "calculated" | "estimated" | "claimed";

export interface Provenance {
  status: ProvenanceStatus;
  source: string;
  engine: string | null;
  engine_version: string | null;
  game: string;
  game_version: string | null;
  snapshot_id: string | null;
  recorded_at: string;
  methodology: string | null;
  context: Record<string, unknown>;
}

export interface Metric {
  key: string;
  value: number | null;
  unit: string | null;
  provenance: Provenance | null;
  unknown_reason: string | null;
}

export interface Item {
  slot: string | null;
  name: string | null;
  base_type: string | null;
  rarity: string | null;
  item_level: number | null;
  lines: string[];
}

export interface SkillGem {
  name: string;
  level: number | null;
  quality: number | null;
  enabled: boolean;
  support: boolean | null;
}

export interface SkillGroup {
  slot: string | null;
  enabled: boolean;
  label: string | null;
  gems: SkillGem[];
}

export interface Tree {
  version: string | null;
  class_id: number | null;
  subclass_id: number | null;
  node_ids: number[];
  mastery_effects: Record<string, number>;
  source_url: string | null;
  unknown_reason: string | null;
}

export interface BuildSnapshot {
  id: string;
  game: string;
  game_version: string | null;
  character: { class_name: string | null; subclass: string | null; level: number | null };
  main_skill: string | null;
  skills: SkillGroup[];
  items: Item[];
  tree: Tree;
  engine_config: Record<string, unknown>;
  metrics: Metric[];
  notes: string | null;
  raw: { kind: string; sha256: string; size_bytes: number; url: string | null };
  created_at: string;
  extra: Record<string, unknown>;
}

export interface ApiError {
  code: string;
  message: string;
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiError,
  ) {
    super(body.message);
  }
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function analyzeBuild(code: string, game?: string): Promise<BuildSnapshot> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/builds/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code, game: game ?? null }),
    });
  } catch {
    throw new ApiRequestError(0, { code: "backend_unreachable", message: "The analysis service is unreachable." });
  }
  if (!res.ok) {
    let body: ApiError = { code: "http_error", message: `HTTP ${res.status}` };
    try {
      const json = await res.json();
      if (json && typeof json.code === "string") body = json;
      else if (json && json.detail) body = { code: "validation_error", message: JSON.stringify(json.detail) };
    } catch {
      /* keep default */
    }
    throw new ApiRequestError(res.status, body);
  }
  const json = (await res.json()) as { snapshot: BuildSnapshot };
  return json.snapshot;
}

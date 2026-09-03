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

export interface Modification {
  kind: string;
  payload: Record<string, unknown>;
}

export interface BuildVariant {
  id: string;
  parent_snapshot_id: string;
  modifications: Modification[];
  snapshot: BuildSnapshot;
  /** The parent re-evaluated by the same engine with no modification — like-for-like deltas. */
  baseline: BuildSnapshot | null;
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

async function post(path: string, body: unknown): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiRequestError(0, { code: "backend_unreachable", message: "The analysis service is unreachable." });
  }
  return res;
}

export async function recalculateBuild(code: string, modifications: Modification[], game?: string): Promise<BuildVariant> {
  const res = await post("/api/v1/builds/recalculate", { code, game: game ?? null, modifications });
  if (!res.ok) throw await toError(res);
  const json = (await res.json()) as { variant: BuildVariant };
  return json.variant;
}

async function toError(res: Response): Promise<ApiRequestError> {
  let body: ApiError = { code: "http_error", message: `HTTP ${res.status}` };
  try {
    const json = await res.json();
    if (json && typeof json.code === "string") body = json;
    else if (json && json.detail) body = { code: "validation_error", message: JSON.stringify(json.detail) };
  } catch {
    /* keep default */
  }
  return new ApiRequestError(res.status, body);
}

export async function analyzeBuild(code: string, game?: string): Promise<BuildSnapshot> {
  const res = await post("/api/v1/builds/analyze", { code, game: game ?? null });
  if (!res.ok) throw await toError(res);
  const json = (await res.json()) as { snapshot: BuildSnapshot };
  return json.snapshot;
}

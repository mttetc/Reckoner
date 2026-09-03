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

export interface SourceInfo {
  kind: string;
  url: string;
  title: string | null;
  parent_url: string | null;
  terms: string | null;
}

export interface BuildSummary {
  snapshot_id: string;
  game: string;
  game_version: string | null;
  character: BuildSnapshot["character"];
  main_skill: string | null;
  metrics: Metric[];
  node_count: number | null;
  created_at: string;
  source: SourceInfo | null;
}

export interface SearchResponse {
  total: number;
  items: BuildSummary[];
}

export interface BuildDetail {
  snapshot: BuildSnapshot;
  source: SourceInfo | null;
}

export interface SearchParams {
  game?: string;
  class_name?: string;
  subclass?: string;
  main_skill?: string;
  game_version?: string;
  min_dps?: number;
  min_life?: number;
  min_ehp?: number;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface KnowledgeMetadata {
  game: string;
  version: string | null;
  patch: string | null;
  season: string | null;
  class_name: string | null;
  source: string;
  source_url: string | null;
  published_at: string | null;
  retrieved_at: string;
}

export interface KnowledgeHit {
  chunk: { id: string; text: string; metadata: KnowledgeMetadata };
  heading: string | null;
  title: string | null;
  score: number;
}

export interface Evidence {
  statement: string;
  provenance: Provenance;
  source_url: string | null;
  excerpt: string | null;
  published_at: string | null;
  retrieved_at: string | null;
}

export interface AskStep {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
  error: string | null;
  duration_ms: number;
}

export interface AskResponse {
  answer: string;
  model: string;
  steps: AskStep[];
  evidence: Evidence[];
  audit: { checked: number; unverified: string[]; clean: boolean };
  degraded: string[];
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
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

async function get(path: string): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiRequestError(0, { code: "backend_unreachable", message: "The analysis service is unreachable." });
  }
}

export async function searchBuilds(params: SearchParams): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== null) qs.set(k, String(v));
  const res = await get(`/api/v1/builds?${qs.toString()}`);
  if (!res.ok) throw await toError(res);
  return (await res.json()) as SearchResponse;
}

export async function getBuild(snapshotId: string): Promise<BuildDetail> {
  const res = await get(`/api/v1/builds/${encodeURIComponent(snapshotId)}`);
  if (!res.ok) throw await toError(res);
  return (await res.json()) as BuildDetail;
}

export async function searchKnowledge(game: string, q: string, k = 8, patch?: string): Promise<KnowledgeHit[]> {
  const qs = new URLSearchParams({ game, q, k: String(k) });
  if (patch) qs.set("patch", patch);
  const res = await get(`/api/v1/knowledge/search?${qs.toString()}`);
  if (!res.ok) throw await toError(res);
  return (await res.json()) as KnowledgeHit[];
}

export async function askReckoner(question: string, game?: string, code?: string): Promise<AskResponse> {
  const res = await post("/api/v1/ask", { question, game: game ?? null, code: code?.trim() ? code : null });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as AskResponse;
}

// Thin client over /api/*. Every function returns real backend data -- no
// mock data, no hardcoded results (STUDIO_AUTORUN.md Never-do list).
const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json()
}

export interface HealthInfo {
  status: string
  git_commit: string
  python: string
  semantic_rule: string
  abi_validation_table: { abi: string; verdict: string; caveat: string }[]
}

export interface TraceSummary {
  id: string
  path: string
  abi: number
  abi_name: string
  controller_name?: string
  kernel_release: string
  n_dominant_events: number
  n_total_events?: number
  n_other_events: number
  duration_s: number | null
  callback_counts: Record<string, number>
  size_bytes: number
  meta: Record<string, unknown> | null
  error?: string
}

export interface TraceDetail extends TraceSummary {
  reference_impl_id?: string
  recorder_version?: number
  sha256?: string
  other_connections?: { n_other_events: number; note: string }
}

export interface SeriesResponse {
  t: number[]
  series: Record<string, (number | null)[]>
  n_total_events_in_window?: number
}

export interface EventsResponse {
  total: number
  offset: number
  limit: number
  events: Record<string, unknown>[]
}

export interface ControllerSummary {
  id: string
  abi: number | null
  kind: string
  description: string
  name: string
  source_editable: boolean
  base?: string
  params?: Record<string, number>
}

export interface ValidationCheck {
  name: string
  ok: boolean
  detail: string
}

export interface ValidationReport {
  ok: boolean
  checks: ValidationCheck[]
  first_2000_divergence?: unknown
  base_reference?: string
  abi?: number
  error?: string
}

export interface DivergenceField {
  reference: unknown
  candidate: unknown
}

export interface Divergence {
  matched_event_count_before_divergence: number
  first_divergent_event: { seq: number; event_index: number }
  callback: string
  callback_result_diff: Record<string, DivergenceField>
  controller_owned_state_diff: Record<string, DivergenceField>
  private_state_diff: Record<string, DivergenceField>
  shared_pre: Record<string, unknown>
  inputs_and_time: Record<string, unknown>
  all_diff_fields: string[]
}

export interface DiffResult {
  trace: string
  reference: string
  candidate: string
  n_events_dominant: number
  matched_event_count_before_divergence: number
  divergence: Divergence | null
  event_context: { seq: number; callback: string }[] | null
  result: 'NO DIVERGENCE' | 'DIVERGENCE'
  kind: 'result' | 'private_state_only' | 'none'
  reference_id: string
  candidate_id: string
  trace_id: string
}

export interface CheckpointResult {
  trace_id: string
  reference_id: string
  candidate_id: string
  interval: number
  n_checkpoints: number
  first_divergence_full_run: { event_index: number; seq: number; callback: string; diff_fields: string[] } | null
  result: 'NO DIVERGENCE' | 'DIVERGENCE'
  nearest_checkpoint?: { event_index: number; seq: number }
  suffix_length?: number
  suffix_replay_divergence?: unknown
  reproduced_same_divergence?: boolean
}

export interface Experiment {
  id: string
  type: string
  config: Record<string, unknown>
  status: 'queued' | 'running' | 'done' | 'error'
  result: (DiffResult & CheckpointResult) | null
  error: string | null
  created_at: number
  started_at: number | null
  finished_at: number | null
}

export const api = {
  health: () => req<HealthInfo>('/health'),
  listTraces: () => req<TraceSummary[]>('/traces'),
  getTrace: (id: string) => req<TraceDetail>(`/traces/${id}`),
  getSeries: (id: string, fields: string[], maxPoints = 4000) =>
    req<SeriesResponse>(`/traces/${id}/series?fields=${fields.join(',')}&max_points=${maxPoints}`),
  getEvents: (id: string, offset = 0, limit = 50, callback?: string) =>
    req<EventsResponse>(
      `/traces/${id}/events?offset=${offset}&limit=${limit}${callback ? `&callback=${callback}` : ''}`
    ),
  uploadTrace: async (file: File, metaFile?: File) => {
    const form = new FormData()
    form.append('file', file)
    if (metaFile) form.append('meta', metaFile)
    const res = await fetch(BASE + '/traces/upload', { method: 'POST', body: form })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(body.detail)
    }
    return res.json() as Promise<TraceDetail>
  },
  listControllers: () => req<ControllerSummary[]>('/controllers'),
  getControllerSource: (id: string) => fetch(`${BASE}/controllers/${id}/source`).then((r) => r.text()),
  getTemplate: (base: string) => fetch(`${BASE}/controllers/templates/${base}`).then((r) => r.text()),
  createParamController: (base: string, name: string, params: Record<string, number>) =>
    req<{ id: string; validation: ValidationReport }>('/controllers/param', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base, name, params }),
    }),
  createUserController: (name: string, abiBase: string, code: string) =>
    req<{ id: string; validation: ValidationReport }>('/controllers/user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, abi_base: abiBase, code }),
    }),
  validateController: (id: string) => req<ValidationReport>(`/controllers/${id}/validate`, { method: 'POST' }),
  createExperiment: (type: string, trace_id: string, reference: string, candidate: string, interval?: number) =>
    req<{ id: string; status: string }>('/experiments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, trace_id, reference, candidate, interval }),
    }),
  getExperiment: (id: string) => req<Experiment>(`/experiments/${id}`),
  listExperiments: () => req<Experiment[]>('/experiments'),
  rerunExperiment: (id: string) =>
    req<{ id: string; status: string; same_as_original: boolean; error: string | null }>(
      `/experiments/${id}/rerun`,
      { method: 'POST' }
    ),
  exportUrl: (id: string, format: 'json' | 'md') => `${BASE}/experiments/${id}/export?format=${format}`,
}

export async function pollExperiment(id: string, onUpdate?: (e: Experiment) => void): Promise<Experiment> {
  for (let i = 0; i < 600; i++) {
    const exp = await api.getExperiment(id)
    onUpdate?.(exp)
    if (exp.status === 'done' || exp.status === 'error') return exp
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error('experiment polling timed out')
}

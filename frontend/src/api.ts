export type Spec = { name?: string; gain_db?: number; components: Comp[]; shape?: { centres: number[]; gains_db: number[] } }
export type Comp = {
  type: string; level: number; weighting?: 'A' | 'Z'; mute?: boolean; custom_id?: string
  params?: Record<string, number>; eq?: { tilt_db_oct?: number; lowcut?: number; highcut?: number; bands?: Record<string, number> }
  mod?: { depth_db?: number; rate_hz?: number; am_depth?: number; am_hz?: number }
}

async function j<T = any>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) {
    let msg = r.statusText
    try { const d = await r.json(); msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail) } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}
const post = (url: string, body?: unknown) =>
  j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  health: () => j('/api/health'),
  presets: () => j('/api/presets'),
  validation: () => j('/api/validation'),
  newWorkspace: () => post('/api/workspace') as Promise<{ id: string }>,
  demo: (w: string, kind: string, level: number, duration = 4) => post(`/api/workspace/${w}/demo?kind=${kind}&level_dba=${level}&duration=${duration}`),
  uploadTarget: (w: string, file: File, f: Record<string, string>) => {
    const fd = new FormData(); fd.append('file', file); Object.entries(f).forEach(([k, v]) => fd.append(k, v))
    return j(`/api/workspace/${w}/target`, { method: 'POST', body: fd })
  },
  uploadBackground: (w: string, file: File) => { const fd = new FormData(); fd.append('file', file); return j(`/api/workspace/${w}/background`, { method: 'POST', body: fd }) },
  uploadMasker: (w: string, file: File) => { const fd = new FormData(); fd.append('file', file); return j(`/api/workspace/${w}/masker-upload`, { method: 'POST', body: fd }) },
  settings: (w: string, s: Record<string, unknown>) => post(`/api/workspace/${w}/settings`, s),
  maskerPreview: (w: string, spec: Spec, duration = 6) => post(`/api/workspace/${w}/masker-preview`, { spec, duration }),
  predict: (w: string, specs: Spec[], p_crit: number, extra: Record<string, unknown> = {}) => post(`/api/workspace/${w}/predict`, { specs, p_crit, ...extra }),
  compare: (w: string, specs: Spec[], p_crit: number, optimise: boolean, lam: number, extra: Record<string, unknown> = {}) =>
    post(`/api/workspace/${w}/compare`, { specs, p_crit, optimise, lam, ...extra }),
  optimiseShape: (w: string, spec: Spec, p_crit: number, lam: number) => post(`/api/workspace/${w}/optimise-shape`, { spec, p_crit, lam }),
  caspStart: (w: string, body: unknown) => post(`/api/workspace/${w}/casp/start`, body) as Promise<{ job: string }>,
  caspGet: (id: string) => j(`/api/casp/${id}`),
  caspCancel: (id: string) => fetch(`/api/casp/${id}`, { method: 'DELETE' }),
  expCreate: (w: string, body: unknown) => post(`/api/workspace/${w}/exp/create`, body),
  expNext: (id: string) => post(`/api/exp/${id}/next`),
  expAnswer: (id: string, index: number, response: string) => post(`/api/exp/${id}/answer`, { index, response }),
  expSummary: (id: string) => j(`/api/exp/${id}/summary`),
  expCompare: (id: string, p_crit: number, quiet_offset_db = 0) => post(`/api/exp/${id}/model-compare`, { p_crit, quiet_offset_db }),
  sessions: () => j('/api/sessions'),
  listenUrl: (w: string, spec: Spec, snr: number | null, o: { spl_fs: number; cap: number; offset?: number; target?: boolean; seed?: number }) =>
    `/api/workspace/${w}/listen.wav?masker=${encodeURIComponent(JSON.stringify(spec))}${snr === null ? '' : `&snr=${snr}`}&target=${o.target === false ? 0 : 1}` +
    `&spl_fs=${o.spl_fs}&cap=${o.cap}&offset=${o.offset ?? 0}&seed=${o.seed ?? 1}`,
  libPut: (specs: Spec[]) => fetch('/api/library', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ specs }) }),
  libDelete: (name: string) => fetch(`/api/library/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  projects: () => j('/api/projects'),
  saveProject: (w: string, name: string, project_id: string | null, ui: unknown) => post(`/api/workspace/${w}/project/save`, { name, project_id, ui }),
  loadProject: (id: string) => post(`/api/project/${id}/load`),
  deleteProject: (id: string) => fetch(`/api/project/${id}`, { method: 'DELETE' }),
  importProject: (file: File) => { const fd = new FormData(); fd.append('file', file); return j('/api/project/import', { method: 'POST', body: fd }) },
  projectDownloadUrl: (id: string) => `/api/project/${id}/download`,
  exportUrl: (w: string, kind: string) => `/api/workspace/${w}/export/${kind}`,
}

export const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined || !isFinite(v as number) ? '—' : (v as number).toFixed(d))

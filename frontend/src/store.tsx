import { createContext, useContext, useEffect, useMemo, useState, ReactNode, useCallback } from 'react'
import { api, Spec } from './api'

export type Safety = { spl_fs: number; cap: number; calibrated: boolean }
type Store = {
  wid: string | null
  setWid: (w: string) => void
  projectName: string
  setProjectName: (n: string) => void
  projectId: string | null
  setProjectId: (n: string | null) => void
  libSaved: number
  target: any | null
  setTarget: (t: any) => void
  presets: any | null
  health: any | null
  specs: Spec[]
  setSpecs: (s: Spec[]) => void
  selected: Set<number>
  setSelected: (s: Set<number>) => void
  pCrit: number
  setPCrit: (p: number) => void
  predict: any | null
  setPredict: (p: any) => void
  compare: any | null
  setCompare: (p: any) => void
  casp: any | null
  setCasp: (p: any) => void
  safety: Safety
  setSafety: (s: Safety) => void
  offsetDb: number
  setOffsetDb: (n: number) => void
  toast: (m: string) => void
  msg: string
  busy: string | null
  run: <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>
  theme: string
  toggleTheme: () => void
}
const Ctx = createContext<Store>(null as any)
export const useStore = () => useContext(Ctx)

export function Provider({ children }: { children: ReactNode }) {
  const [wid, setWid] = useState<string | null>(null)
  const [projectName, setProjectName] = useState('Untitled project')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [libSaved, setLibSaved] = useState(0)
  const [target, setTarget] = useState<any>(null)
  const [presets, setPresets] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [specs, setSpecs] = useState<Spec[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set([0, 3, 4]))
  const [pCrit, setPCrit] = useState(0.6)
  const [predict, setPredict] = useState<any>(null)
  const [compare, setCompare] = useState<any>(null)
  const [casp, setCasp] = useState<any>(null)
  const [safety, setSafety] = useState<Safety>({ spl_fs: 100, cap: 70, calibrated: false })
  const [offsetDb, setOffsetDb] = useState(0)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('aml-theme') || 'dark' } catch { return 'dark' } })

  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem('aml-theme', theme) } catch { /* private mode */ } }, [theme])
  useEffect(() => {
    (async () => {
      try {
        const [w, p, h] = await Promise.all([api.newWorkspace(), api.presets(), api.health()])
        setWid(w.id); setPresets(p); setHealth(h); setSpecs(p.maskers)
      } catch (e: any) { setMsg('Backend not reachable: ' + e.message) }
    })()
  }, [])
  // automatic scene library: every non-default scene is saved on the server a moment after each change
  useEffect(() => {
    if (!presets || !specs.length) return
    const defaults: Record<string, string> = Object.fromEntries((presets.default_specs || []).map((d: Spec) => [d.name, JSON.stringify(d)]))
    const mine = specs.filter(sp => sp.name && defaults[sp.name] !== JSON.stringify(sp))
    if (!mine.length) return
    const t = setTimeout(() => { api.libPut(mine).then(() => setLibSaved(Date.now())).catch(() => 0) }, 1200)
    return () => clearTimeout(t)
  }, [specs, presets])
  const toast = useCallback((m: string) => { setMsg(m); setTimeout(() => setMsg(''), 6000) }, [])
  const run = useCallback(async <T,>(label: string, fn: () => Promise<T>) => {
    setBusy(label)
    try { return await fn() } catch (e: any) { toast(`${label}: ${e.message}`); return undefined } finally { setBusy(null) }
  }, [toast])
  const value = useMemo<Store>(() => ({
    wid, setWid, projectName, setProjectName, projectId, setProjectId, libSaved, target, setTarget, presets, health, specs, setSpecs, selected, setSelected, pCrit, setPCrit, predict, setPredict,
    compare, setCompare, casp, setCasp, safety, setSafety, offsetDb, setOffsetDb, toast, msg, busy, run, theme,
    toggleTheme: () => setTheme(t => (t === 'dark' ? 'light' : 'dark')),
  }), [wid, projectName, projectId, libSaved, target, presets, health, specs, selected, pCrit, predict, compare, casp, safety, offsetDb, msg, busy, run, theme, toast])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

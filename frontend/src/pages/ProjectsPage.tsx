import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, PageHead, Callout } from '../ui'

export default function ProjectsPage({ go }: { go: (p: string) => void }) {
  const s = useStore()
  const [list, setList] = useState<any[]>([])
  const refresh = () => api.projects().then(setList).catch(() => 0)
  useEffect(() => { refresh() }, [])

  const save = async (asNew: boolean) => {
    if (!s.wid) return
    const ui = { specs: s.specs, selected: [...s.selected], pCrit: s.pCrit, offsetDb: s.offsetDb, safety: s.safety }
    const r = await s.run('saving project', () => api.saveProject(s.wid!, s.projectName, asNew ? null : s.projectId, ui))
    if (r) { s.setProjectId(r.project_id); s.toast(`Project saved: ${s.projectName}`); refresh() }
  }
  const load = async (id: string) => {
    const r = await s.run('loading project', () => api.loadProject(id))
    if (!r) return
    s.setWid(r.wid); s.setProjectId(r.project_id); s.setProjectName(r.name)
    s.setTarget(r.target)
    const ui = r.ui || {}
    if (ui.specs?.length) s.setSpecs(ui.specs)
    if (ui.selected) s.setSelected(new Set<number>(ui.selected))
    if (typeof ui.pCrit === 'number') s.setPCrit(ui.pCrit)
    s.setOffsetDb(ui.offsetDb || 0)
    if (ui.safety) s.setSafety(ui.safety)
    const res = r.results || {}
    s.setPredict(res.predict?.items ? { items: res.predict.items, model: 'ERB-EDM (fast)' } : null)
    s.setCompare(res.compare ? { rows: res.compare, model: 'ERB-EDM (fast)' } : null)
    s.setCasp(res.casp || null)
    s.toast(`Loaded “${r.name}”`)
    go(r.target ? 'target' : 'maskers')
  }
  const del = async (id: string) => { if (confirm('Delete this saved project? This cannot be undone.')) { await api.deleteProject(id); refresh() } }
  const imp = async (f: File | null) => { if (!f) return; const r = await s.run('importing project', () => api.importProject(f)); if (r) { refresh(); s.toast('Project imported. Press Load.') } }

  return (
    <div className="page">
      <PageHead title="Projects">Save everything you did (target audio and calibration, distances, event window, scenes, criterion, participant offset, headphone settings and the latest results) and come back to it later. Scenes you build are additionally kept in a shared library that every project can use.</PageHead>
      <div className="grid g2">
        <Card title="Save the current project">
          <div className="stack">
            <div className="field"><label>Project name</label><input type="text" value={s.projectName} onChange={e => s.setProjectName(e.target.value)} /></div>
            <div className="row">
              <button className="btn primary" onClick={() => save(false)} disabled={!s.wid}>{s.projectId ? 'Save (overwrite)' : 'Save project'}</button>
              {s.projectId && <button className="btn" onClick={() => save(true)}>Save as a copy</button>}
            </div>
            <p style={{ fontSize: 12, margin: 0 }}>{s.target ? `Target: ${s.target.source}` : 'No target loaded yet; scenes and settings can still be saved.'} Listening-test sessions are stored separately on the Listening page and are kept automatically.</p>
            <Callout>Saved files are plain folders on this computer (<code>data/projects</code>). Download one as a single <code>.amlproj</code> file to move it to another computer, and import it here.</Callout>
          </div>
        </Card>
        <Card title="Import a project file">
          <div className="field"><label>.amlproj file</label><input type="file" accept=".amlproj,.zip" onChange={e => imp(e.target.files?.[0] || null)} /></div>
        </Card>
      </div>
      <Card title="Saved projects" className="" right={<button className="btn sm ghost" onClick={refresh}>refresh</button>}>
        {!list.length ? <div className="empty">No saved projects yet.</div> :
          <table className="t"><thead><tr><th>Name</th><th>Target</th><th className="n">Scenes</th><th>Saved</th><th /></tr></thead>
            <tbody>{list.map(p => <tr key={p.id}><td>{p.name}{p.id === s.projectId && <span className="tag" style={{ marginLeft: 8 }}>open</span>}</td><td>{p.has_target ? p.source : '—'}</td><td className="n">{p.n_scenes}</td>
              <td>{new Date(p.saved * 1000).toLocaleString()}</td>
              <td className="row" style={{ justifyContent: 'flex-end' }}><button className="btn sm primary" onClick={() => load(p.id)}>Load</button>
                <a className="btn sm" href={api.projectDownloadUrl(p.id)}>Download</a><button className="btn sm ghost" onClick={() => del(p.id)}>Delete</button></td></tr>)}</tbody></table>}
      </Card>
    </div>
  )
}

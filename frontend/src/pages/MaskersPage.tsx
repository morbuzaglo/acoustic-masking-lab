import { useState } from 'react'
import { useStore } from '../store'
import { api, Comp, Spec, fmt } from '../api'
import { Card, Tile, PageHead, Slider, Heat, BandBars, Waveform, Callout, CAT } from '../ui'

const EQ_BANDS = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
const newComp = (type: string): Comp => ({ type, level: 40, weighting: 'A' })

export default function MaskersPage() {
  const s = useStore()
  const [idx, setIdx] = useState(0)
  const [prev, setPrev] = useState<any>(null)
  const [audioUrl, setAudioUrl] = useState('')
  const spec = s.specs[idx]
  const upd = (f: (sp: Spec) => Spec) => { const n = [...s.specs]; n[idx] = f(JSON.parse(JSON.stringify(n[idx]))); s.setSpecs(n); setPrev(null) }
  const updComp = (i: number, f: (c: Comp) => Comp) => upd(sp => { sp.components[i] = f(sp.components[i]); return sp })
  if (!spec) return <div className="page"><p>Loading…</p></div>

  const preview = async () => { const r = await s.run('rendering masker', () => api.maskerPreview(s.wid!, spec, 6)); if (r) setPrev(r) }
  const listen = () => setAudioUrl(api.listenUrl(s.wid!, spec, null, { spl_fs: s.safety.spl_fs, cap: Math.min(s.safety.cap, 60), target: false }) + `&t=${Date.now()}`)
  const addScene = () => { s.setSpecs([...s.specs, { name: `Scene ${s.specs.length + 1}`, components: [newComp('pink')] }]); setIdx(s.specs.length) }
  const del = () => { if (s.specs.length < 2) return; if (spec.name) api.libDelete(spec.name); const n = s.specs.filter((_, i) => i !== idx); s.setSpecs(n); setIdx(0) }
  const upload = async (f: File | null) => {
    if (!f) return
    const r = await s.run('reading masker WAV', () => api.uploadMasker(s.wid!, f))
    if (r) upd(sp => { sp.components.push({ type: 'custom', custom_id: r.custom_id, level: 40, weighting: 'A' }); sp.name = sp.name || r.name; return sp })
  }

  return (
    <div className="page">
      <PageHead title="Maskers">Build the background scenes. Each component is rendered at its own A-weighted level at the receiver; the prediction later scales the <i>whole scene</i> to find the level that reaches your detectability target. Natural sounds are synthesised signal models (SYNTHETIC), or load your own recording.</PageHead>
      <div className="grid g12">
        <Card title="Scenes" right={<button className="btn sm" onClick={addScene}>+ new</button>}>
          <div className="stack">
            {s.specs.map((sp, i) => (
              <div key={i} className="row" style={{ gap: 6 }}>
                <input type="checkbox" checked={s.selected.has(i)} onChange={e => { const n = new Set(s.selected); e.target.checked ? n.add(i) : n.delete(i); s.setSelected(n) }} aria-label={`include ${sp.name} in predictions`} />
                <button className={`btn sm ${i === idx ? 'primary' : ''}`} style={{ flex: 1, justifyContent: 'flex-start' }} onClick={() => { setIdx(i); setPrev(null) }}>
                  <span className="swatch" style={{ background: CAT[i % CAT.length] }} />{sp.name}</button>
              </div>))}
            <p style={{ fontSize: 12, margin: 0 }}>Tick the scenes to include in Predict / Optimise. Scenes you create or edit are <b>saved automatically</b> to your library and reappear in every project{s.libSaved ? ` (saved ${new Date(s.libSaved).toLocaleTimeString()})` : ''}.</p>
          </div>
        </Card>

        <div className="stack">
          <Card title={<input type="text" value={spec.name || ''} onChange={e => upd(sp => { sp.name = e.target.value; return sp })} style={{ fontWeight: 600, maxWidth: 320 }} aria-label="scene name" />}
            right={<><button className="btn sm ghost" onClick={del}>delete scene</button></>}>
            <div className="stack">
              {spec.components.map((c, i) => (
                <div key={i} className="card" style={{ background: 'var(--panel-2)', boxShadow: 'none' }}>
                  <div className="row" style={{ marginBottom: 8 }}>
                    <select value={c.type} onChange={e => updComp(i, c0 => ({ ...c0, type: e.target.value, params: {} }))} style={{ maxWidth: 220 }}>
                      {Object.entries(s.presets?.masker_types || {}).map(([k, l]) => <option key={k} value={k}>{l as string}</option>)}
                      {c.type === 'custom' && <option value="custom">Uploaded WAV</option>}
                    </select>
                    <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={!!c.mute} onChange={e => updComp(i, c0 => ({ ...c0, mute: e.target.checked }))} /> mute</label>
                    <span style={{ flex: 1 }} />
                    {spec.components.length > 1 && <button className="btn sm ghost" onClick={() => upd(sp => { sp.components.splice(i, 1); return sp })}>remove</button>}
                  </div>
                  <div className="grid g3">
                    <Slider label="Level at receiver" v={c.level} set={v => updComp(i, c0 => ({ ...c0, level: v }))} min={0} max={100} unit="dBA" />
                    <Slider label="Spectral tilt" v={c.eq?.tilt_db_oct || 0} set={v => updComp(i, c0 => ({ ...c0, eq: { ...c0.eq, tilt_db_oct: v } }))} min={-6} max={6} step={0.5} unit="dB/oct" digits={1} hint="+ brighter, − darker" />
                    <Slider label="Level fluctuation (std)" v={c.mod?.depth_db || 0} set={v => updComp(i, c0 => ({ ...c0, mod: { ...c0.mod, depth_db: v, rate_hz: c0.mod?.rate_hz || 0.3 } }))} min={0} max={10} step={0.5} unit="dB" digits={1} hint="slow gustiness of the sound" />
                  </div>
                  <details style={{ marginTop: 8 }}><summary>Band equaliser and shaping</summary>
                    <div className="eq" style={{ margin: '8px 0' }}>
                      {EQ_BANDS.map(f => <div className="band" key={f}>
                        <span className="mono">{(c.eq?.bands?.[String(f)] ?? 0).toFixed(0)}</span>
                        <input type="range" min={-24} max={12} step={1} value={c.eq?.bands?.[String(f)] ?? 0} aria-label={`${f} Hz gain`}
                          onChange={e => updComp(i, c0 => ({ ...c0, eq: { ...c0.eq, bands: { ...(c0.eq?.bands || Object.fromEntries(EQ_BANDS.map(b => [String(b), 0]))), [String(f)]: parseFloat(e.target.value) } } }))} />
                        <span>{f >= 1000 ? f / 1000 + 'k' : f}</span></div>)}
                    </div>
                    <div className="grid g2">
                      <Slider label="Low cut" v={c.eq?.lowcut || 0} set={v => updComp(i, c0 => ({ ...c0, eq: { ...c0.eq, lowcut: v || undefined } }))} min={0} max={1000} step={10} unit="Hz" hint="0 = off" />
                      <Slider label="High cut" v={c.eq?.highcut || 0} set={v => updComp(i, c0 => ({ ...c0, eq: { ...c0.eq, highcut: v || undefined } }))} min={0} max={14000} step={100} unit="Hz" hint="0 = off" />
                      <Slider label="Amplitude modulation depth" v={(c.mod?.am_depth || 0) * 100} set={v => updComp(i, c0 => ({ ...c0, mod: { ...c0.mod, am_depth: v / 100, am_hz: c0.mod?.am_hz || 4 } }))} min={0} max={100} unit="%" />
                      <Slider label="Modulation rate" v={c.mod?.am_hz || 4} set={v => updComp(i, c0 => ({ ...c0, mod: { ...c0.mod, am_hz: v } }))} min={0.5} max={40} step={0.5} unit="Hz" digits={1} />
                    </div>
                  </details>
                </div>))}
              <div className="row">
                <button className="btn sm" onClick={() => upd(sp => { sp.components.push(newComp('pink')); return sp })}>+ component</button>
                <label className="btn sm" style={{ cursor: 'pointer' }}>+ upload WAV<input type="file" accept=".wav" hidden onChange={e => upload(e.target.files?.[0] || null)} /></label>
                <span style={{ flex: 1 }} />
                <button className="btn primary" onClick={preview}>Preview scene</button>
                <button className="btn" onClick={listen} title="Safe preview through the headphone calibration, capped at 60 dBA">Listen (safe level)</button>
              </div>
              {audioUrl && <audio controls autoPlay src={audioUrl} style={{ width: '100%' }} />}
              <Callout>Uploaded masker WAVs are treated as <b>relative</b> and rescaled to the level above. Time-stretch and looping use cross-fades; recordings shorter than the analysis window are looped.</Callout>
            </div>
          </Card>

          {prev && <>
            <div className="grid g4">
              <Tile kind="masker" k="LAeq" v={fmt(prev.spectra.LAeq)} u="dBA" />
              <Tile k="Loudness N5 (proxy)" v={fmt(prev.metrics.N5_sone, 2)} u="sone" d="relative comparison only" />
              <Tile k="Sharpness (proxy)" v={fmt(prev.metrics.sharpness_acum, 2)} u="acum" />
              <Tile k="PA proxy" v={fmt(prev.metrics.PA_proxy, 2)} d={`fluctuation ${fmt(prev.metrics.fluct_vacil, 2)} vacil`} />
            </div>
            <div className="grid g2">
              <Card title="Spectrum"><BandBars s={prev.spectra} color="#4fb0e8" height={230} /></Card>
              <Card title="Spectrogram"><Heat z={prev.spectrogram.L} x={prev.spectrogram.t} y={prev.spectrogram.f} colorscale="Viridis" height={230} zmin={0} zmax={Math.max(30, prev.spectra.Lpeak - 30)} /></Card>
            </div>
            <Card title="Waveform"><Waveform w={prev.waveform} color="#4fb0e8" height={160} /></Card>
          </>}
        </div>
      </div>
    </div>
  )
}

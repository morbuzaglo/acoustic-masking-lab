import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, Tile, PageHead, Slider, Plot, Heat, NeedTarget, Callout, CAT, Swatch, Num } from '../ui'

export default function CaspPage() {
  const s = useStore()
  const [job, setJob] = useState<string | null>(null)
  const [info, setInfo] = useState<any>(null)
  const [reps, setReps] = useState(4)
  const [maxDur, setMaxDur] = useState(1.0)
  const [span, setSpan] = useState(8)
  const [val, setVal] = useState<any>(null)
  const timer = useRef<any>(null)
  const chosen = s.specs.map((sp, i) => ({ sp, i })).filter(x => s.selected.has(x.i)).slice(0, 3)
  const pred = s.predict?.items
  const res = s.casp

  useEffect(() => { api.validation().then(setVal).catch(() => 0) }, [])
  useEffect(() => () => clearInterval(timer.current), [])

  // levels around the fast-model estimate when available, otherwise around the preset level
  const grid = () => {
    const centre = pred?.[0]?.required_masker_LAeq != null ? pred[0].required_masker_LAeq - pred[0].masker_LAeq_ref : 0
    return [-1, -0.5, 0, 0.5, 1].map(k => Math.round((centre + k * span) * 2) / 2)
  }
  const start = async () => {
    const r = await s.run('starting CASP', () => api.caspStart(s.wid!, { specs: chosen.map(c => c.sp), gm_db: grid(), realisations: reps, max_duration: maxDur, p_crit: 0.75 }))
    if (!r) return
    setJob(r.job); s.setCasp(null)
    timer.current = setInterval(async () => {
      const i = await api.caspGet(r.job).catch(() => null)
      if (!i) return
      setInfo(i)
      if (i.state === 'done') { clearInterval(timer.current); s.setCasp(i.result) }
      if (i.state === 'error' || i.state === 'cancelled') { clearInterval(timer.current); s.toast(i.error || 'CASP stopped') }
    }, 3000)
  }
  const cancel = async () => { if (job) { await api.caspCancel(job); clearInterval(timer.current); setInfo(null); setJob(null) } }
  const calls = chosen.length * 5 * Math.max(3, reps) * 3
  const running = info && info.state === 'running'

  const fastCurve = (name: string) => pred?.find((p: any) => p.name === name)
  return (
    <div className="page">
      <PageHead title="CASP check (AMT 1.6.0, paulick2024)">The reference model. MATLAB runs the real CASP front end (outer/middle ear, DRNL filterbank, hair-cell stage, adaptation loops, modulation filterbank) and the AMT correlation back end. It takes minutes, so it is used to check the fast model on the scenario you are working on.</PageHead>
      {!s.health?.casp?.available && <Callout kind="bad"><b>MATLAB or AMT not found.</b> Set <code>AML_MATLAB</code> and <code>AML_AMT_ROOT</code> (see README). The rest of the application works without it.</Callout>}
      {!s.target ? <NeedTarget /> : <>
        <div className="grid g21">
          <Card title="Run configuration" sub={`${chosen.length} scene(s) (first three selected), 5 masker levels, ${Math.max(3, reps)} noise realisations → ${calls} CASP evaluations, roughly ${Math.ceil(calls * maxDur * 4 / 60)} min.`}>
            <div className="grid g3">
              <Slider label="Level span" v={span} set={setSpan} min={2} max={16} step={1} unit="dB" hint="steps of ±span/2 around the fast-model estimate" />
              <Num label="Noise realisations" v={reps} set={setReps} min={3} max={8} hint="≥ 3 (leave-one-out reference)" />
              <Num label="Analysed window" unit="s" v={maxDur} set={setMaxDur} step={0.25} min={0.25} max={2} hint="loudest part of the event" />
            </div>
            <p style={{ marginTop: 8, fontSize: 12 }}>Levels (dBA): {chosen[0] ? grid().map(g => ((pred?.[0]?.masker_LAeq_ref ?? 40) + g).toFixed(1)).join(', ') : '—'}{!pred && ' (run Predict first to centre the grid on the fast-model estimate)'}</p>
          </Card>
          <Card title="Job">
            <div className="stack">
              <button className="btn primary big" onClick={start} disabled={!s.health?.casp?.available || !!running || !chosen.length}>Run CASP</button>
              {running && <><div className="progress"><div style={{ width: `${(info.progress || 0) * 100}%` }} /></div><div className="row"><span className="mono">{fmt(info.progress * 100, 0)} %  ·  {fmt(info.elapsed_s, 0)} s</span><button className="btn sm ghost" onClick={cancel}>cancel</button></div></>}
            </div>
          </Card>
        </div>

        {res && <div className="stack" style={{ marginTop: 16 }}>
          <div className="grid g4">
            {res.items.map((it: any, i: number) => {
              const f = fastCurve(it.name)
              return <Tile key={i} kind="model" k={`CASP threshold (P=0.75) · ${it.name}`} v={it.threshold_LAeq === null ? 'out of range' : fmt(it.threshold_LAeq)} u={it.threshold_LAeq === null ? '' : 'dBA'}
                d={f ? `fast model (P=${f.p_crit}) ${fmt(f.required_masker_LAeq)} dBA` : 'run Predict to compare'} />
            })}
          </div>
          <Card title="CASP vs fast model" sub="Solid: CASP with the calibrated decision variance. Dotted: CASP with the unmodified AMT variance (σ² = 40). Dashed: fast model. See the note below on what “calibrated” means.">
            <Plot height={340} data={res.items.flatMap((it: any, i: number) => {
              const col = CAT[chosen[i]?.i % CAT.length]
              const f = fastCurve(it.name)
              return [
                { x: res.levels_LAeq[i], y: it.P_cal, type: 'scatter', mode: 'lines+markers', name: it.name + ' · CASP', line: { color: col, width: 2.6 } },
                { x: res.levels_LAeq[i], y: it.P_raw, type: 'scatter', mode: 'lines', name: it.name + ' · CASP (AMT σ²)', line: { color: col, width: 1.4, dash: 'dot' } },
                ...(f ? [{ x: f.curve_masker.level, y: f.curve_masker.p, type: 'scatter', mode: 'lines', name: it.name + ' · fast', line: { color: col, width: 1.8, dash: 'dash' } }] : [])]
            })}
              layout={{ xaxis: { title: { text: 'Masker LAeq at receiver (dBA)' }, range: [Math.min(...res.levels_LAeq.flat()) - 2, Math.max(...res.levels_LAeq.flat()) + 2] }, yaxis: { title: { text: 'P(correct), 2AFC' }, range: [0.48, 1.01] } }} />
          </Card>
          {res.rep_map?.data && <Card title="CASP internal representation" sub="Output of the adaptation loops (model units) for target + first masker at the middle level, one trace per auditory channel (250–8000 Hz).">
            <Heat z={(res.rep_map.data[0] || []).map((_: any, c: number) => res.rep_map.data.map((row: number[]) => row[c]))} x={res.rep_map.time} y={res.rep_map.fc} colorscale="Magma" height={300} cbtitle="MU" ytitle="Auditory channel (Hz)" />
          </Card>}
        </div>}

        <Card title="How CASP is used here — read before relying on it" className="">
          <div className="stack">
            <p>The CASP <b>front end is the unmodified AMT code</b> (<code>paulick2024.m</code>, 50 DRNL channels 250–8000 Hz). The AMT decision back end was published for intensity discrimination; for noise maskers we use the same correlation-with-template procedure (template = supra-threshold target+masker minus masker, region of interest, leave-one-out reference, mask-only interval from a different noise realisation) and the same mapping P = Φ(0.707 μ/σ), but <b>σ² is re-calibrated</b> so that a 1 kHz tone at a critical ratio of 18 dB reaches P = 0.75 in white noise: σ² = {fmt(res?.in_var_calibrated ?? val?.casp_calibration?.in_var, 0)} versus 40 (AMT default). Without this the raw model is more than 10 dB more sensitive than listeners to tones in noise.</p>
            {val?.casp_validation && <table className="t"><thead><tr><th>Validation scenario</th><th className="n">CASP threshold (masker offset)</th><th className="n">Fast model</th><th className="n">Difference</th></tr></thead>
              <tbody>{Object.entries(val.casp_validation).map(([k, v]: any) => <tr key={k}><td>{k === 'tone1k' ? '1 kHz tone in white noise (calibration anchor)' : '4 kHz tone in white noise (independent check)'}</td>
                <td className="n">{v.casp_thr_gm_db === null ? 'anchor' : fmt(v.casp_thr_gm_db) + ' dB'}</td><td className="n">{v.fast_thr_gm_db === null ? '≈0 (anchor)' : fmt(v.fast_thr_gm_db) + ' dB'}</td>
                <td className="n">{v.casp_thr_gm_db !== null && v.fast_thr_gm_db !== null ? fmt(v.casp_thr_gm_db - v.fast_thr_gm_db) + ' dB' : '—'}</td></tr>)}</tbody></table>}
            <p style={{ fontSize: 12 }}>CASP’s predicted psychometric function is also shallower than the fast model’s (see the validation figure in the documentation). Treat the two models as bracketing the plausible range, and use listening tests with the real stimulus for decisions.</p>
          </div>
        </Card>
      </>}
    </div>
  )
}

import { useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, Tile, PageHead, Slider, Plot, NeedTarget, Callout, CAT, Swatch } from '../ui'

const catColor: Record<string, string> = { natural: '#3fcf8e', synthetic: '#4fb0e8', mixed: '#a594f9', custom: '#f2a93b' }

export default function OptimizePage() {
  const s = useStore()
  const [lam, setLam] = useState(0.5)
  const [opt, setOpt] = useState(false)
  const [shapeIdx, setShapeIdx] = useState(0)
  const [shape, setShape] = useState<any>(null)
  const rows: any[] | undefined = s.compare?.rows
  const chosen = s.specs.filter((_, i) => s.selected.has(i))

  const run = async () => {
    const r = await s.run('comparing maskers', () => api.compare(s.wid!, chosen, s.pCrit, opt, lam, { offset_db: s.offsetDb }))
    if (r) s.setCompare(r)
  }
  const runShape = async () => {
    const r = await s.run('optimising spectrum', () => api.optimiseShape(s.wid!, s.specs[shapeIdx], s.pCrit, lam))
    if (r) setShape(r)
  }
  const ok = rows?.filter(r => r.required_masker_LAeq !== null) || []

  return (
    <div className="page">
      <PageHead title="Compare and optimise">Find the cheapest masker that reaches the detectability target. “Cost” is reported on two separate axes: the added A-weighted level (how much sound you add) and a loudness / annoyance proxy. Neither is a measure of how pleasant the result is.</PageHead>
      {!s.target ? <NeedTarget /> : <>
        <div className="grid g21">
          <Card title="Settings">
            <div className="grid g2">
              <Slider label="Criterion P(2AFC)" v={s.pCrit} set={s.setPCrit} min={0.52} max={0.9} step={0.01} digits={2} />
              <Slider label="Loudness weight λ" v={lam} set={setLam} min={0} max={2} step={0.1} digits={1} hint="0 = minimise dBA only; higher = also penalise loudness N (proxy)" />
            </div>
            <label className="row" style={{ marginTop: 8 }}><input type="checkbox" checked={opt} onChange={e => setOpt(e.target.checked)} /> also optimise the spectral shape of every scene (slower)</label>
          </Card>
          <Card title="Run"><button className="btn primary big" onClick={run} disabled={!chosen.length}>Compare {chosen.length} scenes</button></Card>
        </div>

        {rows && <div className="stack" style={{ marginTop: 16 }}>
          {ok.length > 0 && <div className="grid g4">
            <Tile kind="masker" k="Lowest required level" v={fmt(ok[0].required_masker_LAeq)} u="dBA" d={ok[0].name} />
            <Tile k="Best natural" v={fmt(ok.find(r => r.category === 'natural')?.required_masker_LAeq)} u="dBA" d={ok.find(r => r.category === 'natural')?.name || '—'} />
            <Tile k="Best synthetic" v={fmt(ok.find(r => r.category === 'synthetic')?.required_masker_LAeq)} u="dBA" d={ok.find(r => r.category === 'synthetic')?.name || '—'} />
            <Tile kind="target" k="Target LAeq" v={fmt(s.predict?.items?.[0]?.tgt_LAeq)} u="dBA" d="for reference" />
          </div>}
          <div className="grid g2">
            <Card title="Required masker level" sub="Bars: flat-spectrum scene scaled to the criterion. Diamonds: after spectral optimisation. Error bars: 95 % model range.">
              <Plot height={Math.max(260, 46 * rows.length + 90)} data={[
                { type: 'bar', orientation: 'h', y: rows.map(r => r.name), x: rows.map(r => r.required_masker_LAeq), marker: { color: rows.map(r => catColor[r.category] || '#9aa5b1') }, name: 'flat scene',
                  error_x: { type: 'data', symmetric: false, array: rows.map(r => r.uncertainty.hi95 - r.uncertainty.mean), arrayminus: rows.map(r => r.uncertainty.mean - r.uncertainty.lo95), color: '#9aa5b1', thickness: 1.2 },
                  hovertemplate: '%{y}: %{x:.1f} dBA<extra></extra>' },
                ...(rows.some(r => r.optimised) ? [{ type: 'scatter', mode: 'markers', y: rows.map(r => r.name), x: rows.map(r => r.optimised?.LAeq ?? null), marker: { symbol: 'diamond', size: 11, color: '#fff', line: { color: '#12202d', width: 1.5 } }, name: 'optimised shape', hovertemplate: 'optimised %{x:.1f} dBA<extra></extra>' }] : [])]}
                layout={{ xaxis: { title: { text: 'Masker LAeq at receiver (dBA)' } }, yaxis: { autorange: 'reversed' }, margin: { l: 150, r: 14, t: 8, b: 56 } }} />
              <div className="legend"><span><Swatch c={catColor.natural} />natural</span><span><Swatch c={catColor.synthetic} />synthetic noise</span><span><Swatch c={catColor.mixed} />mixed</span></div>
            </Card>
            <Card title="Level versus annoyance proxy" sub="Each point is a scene at its required level. Lower-left is better on both axes.">
              <Plot height={340} data={ok.map((r, i) => ({ x: [r.required_masker_LAeq], y: [r.metrics?.PA_proxy], type: 'scatter', mode: 'markers+text', text: [r.name], textposition: 'top center', textfont: { size: 10 }, marker: { size: 14, color: catColor[r.category] || '#9aa5b1', line: { color: '#fff', width: 1.5 } }, name: r.name, showlegend: false, hovertemplate: r.name + '<br>%{x:.1f} dBA, PA %{y:.1f}<extra></extra>' }))}
                layout={{ xaxis: { title: { text: 'Required LAeq (dBA)' } }, yaxis: { title: { text: 'PA proxy (relative)' } } }} />
            </Card>
          </div>
          <Card title="Table" sub="N5, sharpness, fluctuation and PA are proxies built on the model's ERB excitation, calibrated to the reference stimuli; use them for ranking, not as standard values.">
            <table className="t"><thead><tr><th>Scene</th><th>Type</th><th className="n">Required</th><th className="n">95 % range</th><th className="n">N5 sone</th><th className="n">Sharp.</th><th className="n">Fluct.</th><th className="n">PA</th><th className="n">Optimised</th><th className="n">Saving</th></tr></thead>
              <tbody>{rows.map((r, i) => <tr key={i}><td>{r.name}</td><td><span className={`tag ${r.category}`}>{r.category}</span></td>
                <td className="n">{r.already_below_threshold ? 'not needed' : r.unreachable ? 'not reachable' : fmt(r.required_masker_LAeq)}</td><td className="n">{fmt(r.uncertainty.lo95)} … {fmt(r.uncertainty.hi95)}</td>
                <td className="n">{fmt(r.metrics?.N5_sone, 2)}</td><td className="n">{fmt(r.metrics?.sharpness_acum, 2)}</td><td className="n">{fmt(r.metrics?.fluct_vacil, 2)}</td><td className="n">{fmt(r.metrics?.PA_proxy, 2)}</td>
                <td className="n">{fmt(r.optimised?.LAeq)}</td><td className="n">{r.optimised ? fmt(r.optimised.saving_dBA) + ' dB' : '—'}</td></tr>)}</tbody></table>
          </Card>
        </div>}

        <Card title="Spectral shape optimiser" className="" sub="Re-weights 12 spectral bands of one scene to minimise added dBA (+ λ·loudness) under the detectability constraint.">
          <div className="row"><select value={shapeIdx} onChange={e => setShapeIdx(+e.target.value)} style={{ maxWidth: 260 }}>{s.specs.map((sp, i) => <option key={i} value={i}>{sp.name}</option>)}</select>
            <button className="btn primary" onClick={runShape}>Optimise this scene</button></div>
          {shape && (shape.ok ? <div className="stack" style={{ marginTop: 12 }}>
            <div className="grid g4">
              <Tile kind="masker" k="Optimised LAeq" v={fmt(shape.LAeq)} u="dBA" d={`flat scene: ${fmt(shape.flat.LAeq)} dBA`} />
              <Tile k="Saving" v={fmt(shape.flat.LAeq - shape.LAeq)} u="dB" d="added level avoided" />
              <Tile k="Loudness N5 proxy" v={fmt(shape.metrics_optimised.N5_sone, 2)} u="sone" d={`flat: ${fmt(shape.metrics_flat.N5_sone, 2)}`} />
              <Tile kind="model" k="P(2AFC) achieved" v={fmt(shape.P2AFC, 3)} d={`criterion ${s.pCrit.toFixed(2)}`} />
            </div>
            <div className="row"><button className="btn primary" onClick={() => {
              const base = s.specs[shapeIdx]; const ns = { ...JSON.parse(JSON.stringify(base)), name: `${base.name} (optimised, P≤${s.pCrit.toFixed(2)})`, shape: { centres: shape.centres, gains_db: shape.gains_db } }
              s.setSpecs([...s.specs, ns]); s.toast('Saved as a new scene in your library. It can now be checked with CASP (CASP check page).') }}>Save optimised shape as a scene</button>
              <span style={{ color: 'var(--ink-3)' }}>The scene keeps the optimised spectrum (levels as found), is stored in your library, and can be run through CASP for verification.</span></div>
            <Plot height={320} data={[
              { x: shape.target_spectrum.fc.map(String), y: shape.target_spectrum.L, type: 'scatter', mode: 'lines+markers', name: 'target', line: { color: '#E69F00', width: 2.4 } },
              { x: shape.masker_spectrum_flat.fc.map(String), y: shape.masker_spectrum_flat.L, type: 'scatter', mode: 'lines', name: 'masker, flat shape', line: { color: '#56B4E9', width: 2, dash: 'dot' } },
              { x: shape.masker_spectrum_opt.fc.map(String), y: shape.masker_spectrum_opt.L, type: 'scatter', mode: 'lines', name: 'masker, optimised', line: { color: '#009E73', width: 2.8 } }]}
              layout={{ xaxis: { type: 'category', title: { text: '1/3-octave band (Hz)' }, tickangle: -60, tickfont: { size: 10 } }, yaxis: { title: { text: 'dB re 20 µPa' } }, margin: { l: 56, r: 10, t: 8, b: 70 } }} />
          </div> : <Callout kind="warn" >{shape.reason}</Callout>)}
        </Card>
      </>}
    </div>
  )
}

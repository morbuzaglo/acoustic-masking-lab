import { useMemo, useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, Tile, PageHead, Slider, Plot, Heat, NeedTarget, Callout, CAT, Swatch } from '../ui'

const dprime = (p: number) => {
  // inverse of P = Phi(d'/sqrt2) via bisection (no dependency)
  const phi = (x: number) => 0.5 * (1 + erf(x / Math.SQRT2))
  let lo = 0, hi = 6
  for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; phi(m / Math.SQRT2) < p ? (lo = m) : (hi = m) }
  return (lo + hi) / 2
}
function erf(x: number) { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y }

export default function PredictPage() {
  const s = useStore()
  const [audio, setAudio] = useState('')
  const [info, setInfo] = useState('')
  const chosen = useMemo(() => s.specs.map((sp, i) => ({ sp, i })).filter(x => s.selected.has(x.i)), [s.specs, s.selected])
  const res = s.predict
  const run = async () => {
    if (!s.wid || !chosen.length) return
    const r = await s.run('predicting detectability', () => api.predict(s.wid!, chosen.map(c => c.sp), s.pCrit, { include_map: true, offset_db: s.offsetDb }))
    if (r) s.setPredict(r)
  }
  const first = res?.items?.[0]
  const idx0 = chosen[0]?.i ?? 0

  const listen = (kind: 'masked' | 'ref') => {
    if (!first || !chosen[0]) return
    const snr = kind === 'masked' ? first.snr_at_threshold : null
    const url = api.listenUrl(s.wid!, chosen[0].sp, snr, { spl_fs: s.safety.spl_fs, cap: s.safety.cap, target: kind === 'masked' })
    fetch(url + `&t=${Date.now()}`).then(r => { setInfo(`Presented at ${r.headers.get('X-Presented-LAeq')} dBA (reduced by ${r.headers.get('X-Reduced-dB')} dB from the physical level)`); return r.blob() }).then(b => setAudio(URL.createObjectURL(b)))
  }

  const curves = res ? res.items.map((it: any, i: number) => ([
    { x: it.curve_masker.level, y: it.curve_masker.p, type: 'scatter', mode: 'lines', name: it.name, line: { color: CAT[chosen[i].i % CAT.length], width: 2.4 }, hovertemplate: '%{x:.0f} dBA → P=%{y:.2f}<extra>' + it.name + '</extra>' },
  ])).flat() : []
  const crit = res?.items?.[0]?.p_crit ?? s.pCrit
  const snrCurves = res ? res.items.map((it: any, i: number) => ({ x: it.curve_snr.snr, y: it.curve_snr.p, type: 'scatter', mode: 'lines', name: it.name, line: { color: CAT[chosen[i].i % CAT.length], width: 2.4 } })) : []

  return (
    <div className="page">
      <PageHead title="Predicted detectability">Fast model (ERB excitation + energy detector, calibrated to the critical ratio): probability of a correct response in a two-alternative forced choice, P(2AFC) = Φ(d′/√2). Chance is 0.5. The required level is where P equals your detectability target.</PageHead>
      {!s.target ? <NeedTarget /> : <>
        <div className="grid g21">
          <Card title="Detectability target" sub="Pick how detectable you tolerate the target to be. Lower P = more masking needed.">
            <div className="grid g2">
              <Slider label="Criterion P(2AFC)" v={s.pCrit} set={s.setPCrit} min={0.52} max={0.9} step={0.01} digits={2} hint={`d′ = ${dprime(s.pCrit).toFixed(2)}.  0.50 = chance, 0.75 ≈ conventional threshold, 0.60 ≈ barely above chance.`} />
              <div className="field"><label>Scenes included</label>
                <div className="legend">{chosen.map(c => <span key={c.i}><Swatch c={CAT[c.i % CAT.length]} />{c.sp.name}</span>)}</div>
                <span className="hint">Change the selection on the Maskers page.</span></div>
            </div>
            {s.offsetDb !== 0 && <Callout>Participant calibration is active: required levels are shifted by <b>{s.offsetDb > 0 ? '+' : ''}{s.offsetDb.toFixed(1)} dB</b> (from your listening test).</Callout>}
          </Card>
          <Card title="Run"><div className="stack"><button className="btn primary big" onClick={run} disabled={!chosen.length}>Predict {chosen.length} scene{chosen.length === 1 ? '' : 's'}</button>
            <p style={{ margin: 0, fontSize: 12 }}>Each synthetic scene is evaluated with 3 independent noise realisations; uncertainty = realisation spread + 3 dB model-form term.</p></div></Card>
        </div>

        {res && first && <div className="stack" style={{ marginTop: 16 }}>
          {res.items.filter((it: any) => it.unreachable).map((it: any) => <Callout key={it.name} kind="bad"><b>{it.name}: not reachable.</b> Even 80 dB above its preset level (≈ {fmt(it.masker_LAeq_ref + 80, 0)} dBA) the predicted P stays at {fmt(it.P_at_plus80, 2)}: this masker has no energy where the target is detected (for example, a high-frequency-only masker cannot hide a low-frequency thump). Reshape the spectrum or choose another masker.</Callout>)}
          {first.already_below_threshold && <Callout kind="warn"><b>{first.name}:</b> the target is already at or below the criterion without any masker (absolute threshold in quiet). No masker needed in this model.</Callout>}
          <div className="grid g4">
            <Tile kind="masker" k={`Required masker · ${first.name}`} v={first.required_masker_LAeq === null ? '—' : fmt(first.required_masker_LAeq)} u="dBA" d={`95 % range ${fmt(first.uncertainty.lo95)} … ${fmt(first.uncertainty.hi95)}`} />
            <Tile kind="target" k="Target LAeq (event)" v={fmt(first.tgt_LAeq)} u="dBA" d="at the receiver" />
            <Tile k="SNR at the criterion" v={first.snr_at_threshold === null ? '—' : fmt(first.snr_at_threshold)} u="dB" d="LAeq target − LAeq masker" />
            <Tile kind="model" k="P without masker" v={fmt(first.P_without_masker, 2)} d={`quiet threshold only · scene at nominal level: ${fmt(first.P_at_nominal, 2)}`} />
          </div>

          <div className="grid g2">
            <Card title="Detection versus masker level" sub="P(2AFC) as the whole scene is scaled. The dashed line is your criterion.">
              <Plot height={320} data={[...curves,
                { x: [first.curve_masker.level[0], first.curve_masker.level.at(-1)], y: [crit, crit], type: 'scatter', mode: 'lines', line: { color: '#9aa5b1', dash: 'dash', width: 1.2 }, showlegend: false, hoverinfo: 'skip' },
                ...res.items.filter((it: any) => it.required_masker_LAeq !== null).map((it: any, i: number) => ({ x: [it.required_masker_LAeq], y: [crit], type: 'scatter', mode: 'markers', marker: { size: 10, color: CAT[chosen[i].i % CAT.length], line: { color: '#fff', width: 1.5 } }, showlegend: false, hovertemplate: it.name + ' required: %{x:.1f} dBA<extra></extra>' }))]}
                layout={{ xaxis: { title: { text: 'Masker LAeq at receiver (dBA)' } }, yaxis: { title: { text: 'P(correct), 2AFC' }, range: [0.48, 1.01] }, legend: { orientation: 'h', y: -0.25 } }} />
            </Card>
            <Card title="Detection versus SNR" sub="Same data on the SNR axis (target LAeq − masker LAeq). Steeper = the target emerges more abruptly.">
              <Plot height={320} data={[...snrCurves, { x: [first.curve_snr.snr[0], first.curve_snr.snr.at(-1)], y: [crit, crit], type: 'scatter', mode: 'lines', line: { color: '#9aa5b1', dash: 'dash', width: 1.2 }, showlegend: false, hoverinfo: 'skip' }]}
                layout={{ xaxis: { title: { text: 'SNR (dB)' } }, yaxis: { title: { text: 'P(correct), 2AFC' }, range: [0.48, 1.01] }, legend: { orientation: 'h', y: -0.25 } }} />
            </Card>
          </div>

          {first.map && <div className="grid g21">
            <Card title={`Masking map · ${first.name}`} sub="Target-to-(masker + internal noise) ratio per ERB channel and 5 ms frame, masker at its preset level. Bright cells are where the target stands out; this is where detection happens.">
              <Heat z={first.map.snr_db} x={first.map.t} y={first.map.fc.map((_: number, i: number) => i)} ylog={false} zmin={-40} zmax={30} colorscale="Viridis" height={340} ytitle="ERB channel centre frequency (Hz)" cbtitle="SNR dB" ticks={{ vals: first.map.fc.map((_: number, i: number) => i).filter((i: number) => i % 5 === 0), text: first.map.fc.filter((_: number, i: number) => i % 5 === 0).map((f: number) => String(Math.round(f))) }} />
            </Card>
            <Card title="Where is it detected?" sub="Share of d′² per auditory channel (fast model).">
              <Plot height={340} data={[{ type: 'bar', x: first.fc.map((f: number) => String(Math.round(f))), y: first.channel_share.map((v: number) => v * 100), marker: { color: '#a594f9' }, hovertemplate: '%{x} Hz: %{y:.1f} %<extra></extra>' }]}
                layout={{ xaxis: { type: 'category', title: { text: 'Channel centre (Hz)' }, tickangle: -70, tickfont: { size: 9 } }, yaxis: { title: { text: '% of d′²' } }, margin: { l: 56, r: 10, t: 8, b: 70 } }} />
            </Card>
          </div>}

          <Card title="Results" sub="Required masker LAeq at the receiver for P ≤ criterion.">
            <table className="t"><thead><tr><th>Scene</th><th>Type</th><th className="n">Required LAeq</th><th className="n">95 % range</th><th className="n">SNR</th><th className="n">N5 proxy</th><th className="n">PA proxy</th></tr></thead>
              <tbody>{res.items.map((it: any, i: number) => <tr key={i}><td><Swatch c={CAT[chosen[i].i % CAT.length]} />{it.name}</td><td><span className={`tag ${it.category}`}>{it.category}</span></td>
                <td className="n">{it.already_below_threshold ? 'not needed' : it.unreachable ? 'not reachable' : fmt(it.required_masker_LAeq)}</td><td className="n">{it.already_below_threshold || it.unreachable ? '—' : `${fmt(it.uncertainty.lo95)} … ${fmt(it.uncertainty.hi95)}`}</td>
                <td className="n">{fmt(it.snr_at_threshold)}</td><td className="n">{fmt(it.masker_metrics_at_required?.N5_sone, 2)}</td><td className="n">{fmt(it.masker_metrics_at_required?.PA_proxy, 2)}</td></tr>)}</tbody></table>
            <p style={{ fontSize: 12, marginTop: 8 }}>The 95 % range combines masker-realisation spread and a 3 dB model-form term. It is a model uncertainty, not a confidence interval on a listener population (inter-listener spread is typically a further 2–4 dB).</p>
          </Card>

          <Card title="Hear it" sub="Headphone-safe previews, capped at the level set on the Listening page (default 70 dBA). If the physical level exceeds the cap, target and masker are scaled together so the SNR is preserved.">
            <div className="row"><button className="btn" onClick={() => listen('ref')}>Masker only</button><button className="btn primary" onClick={() => listen('masked')}>Masker + target at the criterion SNR</button><span style={{ color: 'var(--ink-3)' }}>{info}</span></div>
            {audio && <audio controls autoPlay src={audio} style={{ width: '100%', marginTop: 10 }} />}
          </Card>
        </div>}
      </>}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, Tile, PageHead, Slider, Plot, NeedTarget, Callout, Num, Tabs } from '../ui'

type Trial = { index: number; capped: boolean; presented_top_dba: number; limited: boolean }

export default function ListenPage() {
  const s = useStore()
  const [part, setPart] = useState('P01')
  const [maskIdx, setMaskIdx] = useState(0)
  const [method, setMethod] = useState<'staircase' | 'constant'>('staircase')
  const [rule, setRule] = useState('2down1up')
  const [tracks, setTracks] = useState(2)
  const [revs, setRevs] = useState(10)
  const [start, setStart] = useState(6)
  const [levels, setLevels] = useState('-24,-18,-12,-6,0')
  const [reps, setReps] = useState(10)
  const [offset, setOffset] = useState(0)
  const [feedback, setFeedback] = useState(false)
  const [ack, setAck] = useState(false)
  const [sid, setSid] = useState<string | null>(null)
  const [trial, setTrial] = useState<Trial | null>(null)
  const [played, setPlayed] = useState<{ A: boolean; B: boolean }>({ A: false, B: false })
  const [playing, setPlaying] = useState<'A' | 'B' | null>(null)
  const [chosen, setChosen] = useState<string | null>(null)
  const [hist, setHist] = useState<{ n: number; snr: number; ok: boolean }[]>([])
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<any>(null)
  const [cmp, setCmp] = useState<any>(null)
  const [fb, setFb] = useState('')
  const audio = useRef<HTMLAudioElement | null>(null)
  const sessions = useRef<any[]>([])
  const [, force] = useState(0)

  useEffect(() => { api.sessions().then(r => { sessions.current = r; force(x => x + 1) }).catch(() => 0) }, [done])
  useEffect(() => () => { audio.current?.pause() }, [])

  const create = async () => {
    const body: any = {
      participant: part, spec: s.specs[maskIdx], method, rule, n_tracks: tracks, n_reversals: revs, start_snr: start,
      levels: levels.split(',').map(x => parseFloat(x)).filter(x => !isNaN(x)), reps, spl_at_full_scale_db: s.safety.spl_fs, calibrated: s.safety.calibrated,
      cap_dba: s.safety.cap, level_offset_db: offset, p_crit: method === 'staircase' ? (rule === '3down1up' ? 0.794 : 0.707) : 0.75,
    }
    const r = await s.run('creating session', () => api.expCreate(s.wid!, body))
    if (!r) return
    setSid(r.id); setHist([]); setDone(false); setSummary(null); setCmp(null)
    await next(r.id)
  }
  const next = async (id: string) => {
    const t = await s.run('next trial', () => api.expNext(id))
    if (!t) return
    setChosen(null); setPlayed({ A: false, B: false }); setFb('')
    if (t.done) { setDone(true); setTrial(null); setSummary(t.summary) } else setTrial(t)
  }
  const play = (w: 'A' | 'B') => {
    if (!sid || !trial) return
    audio.current?.pause()
    const a = new Audio(`/api/exp/${sid}/stim/${trial.index}/${w}.wav?t=${Date.now()}`)
    audio.current = a
    a.volume = 1
    setPlaying(w)
    a.onended = () => { setPlaying(null); setPlayed(p => ({ ...p, [w]: true })) }
    a.onerror = () => { setPlaying(null); s.toast('could not load stimulus') }
    a.play().catch(() => setPlaying(null))
  }
  const answer = async (w: 'A' | 'B') => {
    if (!sid || !trial || chosen) return
    setChosen(w)
    const r = await s.run('saving answer', () => api.expAnswer(sid, trial.index, w))
    if (!r) return
    if (feedback) setFb(r.correct ? 'Correct' : 'Incorrect')
    setHist(h => [...h, { n: h.length + 1, snr: r.progress.current ? NaN : NaN, ok: r.correct }])
    setTimeout(() => next(sid), feedback ? 700 : 150)
  }
  // keyboard: 1/2 play, A/B answer (only after both heard)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!trial || (e.target as HTMLElement)?.tagName === 'INPUT') return
      if (e.key === '1') play('A'); if (e.key === '2') play('B')
      if (played.A && played.B) { if (e.key.toLowerCase() === 'a') answer('A'); if (e.key.toLowerCase() === 'b') answer('B') }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  })
  const finish = async () => {
    if (!sid) return
    const sm = await s.run('summary', () => api.expSummary(sid)); if (sm) setSummary(sm)
    const c = await s.run('comparing with the model', () => api.expCompare(sid, method === 'staircase' ? (rule === '3down1up' ? 0.794 : 0.707) : 0.75, 0))
    if (c) setCmp(c)
  }
  useEffect(() => { if (done && sid) finish() }, [done])

  const stair = summary?.trials?.length ? summary.trials : []
  return (
    <div className="page">
      <PageHead title="Listening test (blinded 2AFC)">Two intervals, both contain the masker; one also contains the target. Choose the interval with the target. Which interval is which, and the answer key, stay on the server. An adaptive staircase finds your threshold; the psychometric curve is fitted to all answers and compared with the model.</PageHead>
      {!s.target ? <NeedTarget /> : <>
        {!sid && <div className="grid g2">
          <Card title="1 · Headphones and safe volume" sub="The physical receiver level is reproduced through the headphones only as far as the safety cap allows.">
            <div className="stack">
              <Callout kind="warn"><b>Hearing safety.</b> Start with the system volume low. A 3-second noise burst is never played at more than the cap below; the hard limit is 85 dBA and cannot be raised. Stop at any discomfort.</Callout>
              <Slider label="Headphone sensitivity: SPL of a full-scale sine" v={s.safety.spl_fs} set={v => s.setSafety({ ...s.safety, spl_fs: v })} min={80} max={125} unit="dB" hint="Measure with a coupler/artificial ear. If unknown, leave 100 and keep 'calibrated' off: levels are then only nominal." />
              <label className="row"><input type="checkbox" checked={s.safety.calibrated} onChange={e => s.setSafety({ ...s.safety, calibrated: e.target.checked })} /> headphone sensitivity was measured (levels are absolute)</label>
              <Slider label="Safety cap on presented LAeq" v={s.safety.cap} set={v => s.setSafety({ ...s.safety, cap: v })} min={40} max={85} unit="dBA" hint="Target and masker are scaled down together if the physical level exceeds the cap (SNR preserved)." />
              <Slider label="Level offset" v={offset} set={setOffset} min={-30} max={10} unit="dB" hint="presentation − receiver level; 0 = physical level" />
            </div>
          </Card>
          <Card title="2 · Session">
            <div className="stack">
              <div className="grid g2"><div className="field"><label>Participant</label><input type="text" value={part} onChange={e => setPart(e.target.value)} /></div>
                <div className="field"><label>Masker scene</label><select value={maskIdx} onChange={e => setMaskIdx(+e.target.value)}>{s.specs.map((sp, i) => <option key={i} value={i}>{sp.name}</option>)}</select></div></div>
              <Tabs items={[['staircase', 'Adaptive staircase'], ['constant', 'Constant stimuli']]} v={method} set={setMethod} />
              {method === 'staircase' ? <div className="grid g2">
                <div className="field"><label>Rule</label><select value={rule} onChange={e => setRule(e.target.value)}><option value="2down1up">2-down / 1-up (70.7 %)</option><option value="3down1up">3-down / 1-up (79.4 %)</option></select></div>
                <Num label="Start SNR" unit="dB" v={start} set={setStart} /><Num label="Interleaved tracks" v={tracks} set={setTracks} min={1} max={4} /><Num label="Reversals per track" v={revs} set={setRevs} min={6} max={16} />
              </div> : <div className="grid g2"><div className="field"><label>SNR levels (dB, comma separated)</label><input type="text" value={levels} onChange={e => setLevels(e.target.value)} /></div><Num label="Repetitions per level" v={reps} set={setReps} min={4} max={40} /></div>}
              <p style={{ fontSize: 12, margin: 0 }}>SNR = LAeq of the target clip − LAeq of the masker, at the receiver. Expect 60–120 trials for a staircase session (~10 min).</p>
              <label className="row"><input type="checkbox" checked={feedback} onChange={e => setFeedback(e.target.checked)} /> show correct / incorrect after each trial</label>
              <label className="row"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} /> I set the volume low and understand the safety limits</label>
              <button className="btn primary big" disabled={!ack} onClick={create}>Start session</button>
            </div>
          </Card>
        </div>}

        {sid && !done && trial && <div className="stack">
          <Card title={`Trial ${trial.index + 1}`} right={<span className="chip">{s.safety.calibrated ? 'calibrated' : 'nominal levels'} · ≤ {trial.presented_top_dba.toFixed(0)} dBA{trial.capped ? ' (capped)' : ''}</span>}
            sub="Play both intervals (keys 1 and 2) then pick the one that contains the target (keys A and B).">
            <div className="row" style={{ alignItems: 'stretch' }}>
              <button className={`ab-btn ${playing === 'A' ? 'playing' : ''} ${chosen === 'A' ? 'chosen' : ''}`} onClick={() => play('A')} aria-label="play interval A">A<small>{played.A ? 'heard' : 'press to play'} · <span className="kbd">1</span></small></button>
              <button className={`ab-btn ${playing === 'B' ? 'playing' : ''} ${chosen === 'B' ? 'chosen' : ''}`} onClick={() => play('B')} aria-label="play interval B">B<small>{played.B ? 'heard' : 'press to play'} · <span className="kbd">2</span></small></button>
            </div>
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn primary big" style={{ flex: 1, justifyContent: 'center' }} disabled={!(played.A && played.B) || !!chosen} onClick={() => answer('A')}>The target is in A <span className="kbd">A</span></button>
              <button className="btn primary big" style={{ flex: 1, justifyContent: 'center' }} disabled={!(played.A && played.B) || !!chosen} onClick={() => answer('B')}>The target is in B <span className="kbd">B</span></button>
            </div>
            <div style={{ minHeight: 24, marginTop: 8, color: fb === 'Correct' ? 'var(--good)' : 'var(--bad)' }}>{fb}</div>
            {trial.limited && <Callout kind="warn">The peak limiter reduced this trial slightly (digital headroom).</Callout>}
          </Card>
          <div className="row"><span className="chip">{hist.length} answered</span><button className="btn sm ghost" onClick={() => setDone(true)}>Finish now</button></div>
        </div>}

        {summary && cmp && <div className="stack" style={{ marginTop: 6 }}>
          <div className="grid g4">
            <Tile kind="human" k="Human threshold" v={fmt(cmp.human_threshold)} u="dB SNR" d={`95 % CI ${fmt(cmp.human_ci95[0])} … ${fmt(cmp.human_ci95[1])}`} />
            <Tile kind="model" k="Model threshold" v={fmt(cmp.model_threshold)} u="dB SNR" d={`±${fmt(cmp.model_sd_mc)} (noise draws)`} />
            <Tile kind="accent" k="Participant offset" v={`${cmp.offset_db > 0 ? '+' : ''}${fmt(cmp.offset_db)}`} u="dB" d="human − model" />
            <Tile k="Trials" v={summary.n_trials} d={`${fmt(100 * summary.pc, 0)} % correct overall`} />
          </div>
          <div className="grid g2">
            <Card title="Psychometric function" sub="Points: proportion correct per SNR (area ∝ trials). Orange: fit with 95 % bootstrap threshold CI. Violet: fast-model prediction.">
              <Plot height={340} data={[
                { x: cmp.model_curve.x, y: cmp.model_curve.p, type: 'scatter', mode: 'lines', name: 'model (fast)', line: { color: '#a594f9', width: 2.4, dash: 'dash' } },
                { x: cmp.psychometric.curve.x, y: cmp.psychometric.curve.p, type: 'scatter', mode: 'lines', name: 'human fit', line: { color: '#ff7a59', width: 2.8 } },
                { x: cmp.psychometric.levels, y: cmp.psychometric.k.map((k: number, i: number) => k / cmp.psychometric.n[i]), type: 'scatter', mode: 'markers', name: 'data', marker: { color: '#ff7a59', size: cmp.psychometric.n.map((n: number) => 6 + Math.sqrt(n) * 2), line: { color: '#fff', width: 1.2 } } },
                { x: [cmp.human_threshold], y: [cmp.p_crit], type: 'scatter', mode: 'markers', name: 'threshold', marker: { symbol: 'diamond', size: 12, color: '#fff', line: { color: '#ff7a59', width: 2 } }, error_x: { type: 'data', symmetric: false, array: [cmp.human_ci95[1] - cmp.human_threshold], arrayminus: [cmp.human_threshold - cmp.human_ci95[0]] } }]}
                layout={{ xaxis: { title: { text: 'SNR (dB)' } }, yaxis: { title: { text: 'P(correct)' }, range: [0.4, 1.02] }, shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0.5, y1: 0.5, line: { color: '#9aa5b1', width: 1, dash: 'dot' } }] }} />
            </Card>
            <Card title="Track" sub="Presented SNR per trial; green = correct.">
              <Plot height={340} data={[{ x: stair.map((t: any) => t.index + 1), y: stair.map((t: any) => t.snr_db), type: 'scatter', mode: 'lines+markers', line: { color: '#9aa5b1', width: 1 },
                marker: { color: stair.map((t: any) => (t.correct ? '#3fcf8e' : '#ff6b6b')), size: 7 }, name: 'SNR', hovertemplate: 'trial %{x}: %{y:.1f} dB<extra></extra>' }]}
                layout={{ xaxis: { title: { text: 'Trial' } }, yaxis: { title: { text: 'SNR (dB)' } } }} />
            </Card>
          </div>
          <Card title="Participant-specific calibration">
            <div className="row"><p style={{ margin: 0, flex: 1 }}>This participant needs <b>{fmt(Math.abs(cmp.offset_db))} dB {cmp.offset_db > 0 ? 'more' : 'less'} SNR</b> than the model predicts (95 % range {fmt(cmp.offset_ci95[0])} … {fmt(cmp.offset_ci95[1])} dB). Applying it shifts all required masker levels on the Predict and Optimise pages, for this masker type and listening condition only.</p>
              <button className="btn primary" onClick={() => { s.setOffsetDb(-cmp.offset_db); s.toast(`Participant offset applied: masker levels ${cmp.offset_db > 0 ? 'lowered' : 'raised'} by ${Math.abs(cmp.offset_db).toFixed(1)} dB`) }}>Apply to predictions</button>
              <button className="btn" onClick={() => { setSid(null); setTrial(null); setDone(false); setSummary(null); setCmp(null) }}>New session</button></div>
          </Card>
        </div>}
        {done && !cmp && <div className="empty"><div><span className="spinner" /> Fitting the psychometric function… (needs at least 12 trials at 3 levels)</div></div>}

        <Card title="Saved sessions" className="">
          <table className="t"><thead><tr><th>Id</th><th>Participant</th><th>Method</th><th className="n">Trials</th><th>Date</th></tr></thead>
            <tbody>{sessions.current.map((x: any) => <tr key={x.id}><td className="mono">{x.id}</td><td>{x.participant}</td><td>{x.method}</td><td className="n">{x.n_trials}</td><td>{new Date(x.created * 1000).toLocaleString()}</td></tr>)}</tbody></table>
        </Card>
      </>}
    </div>
  )
}

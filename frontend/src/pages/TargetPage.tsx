import { useState } from 'react'
import { useStore } from '../store'
import { api, fmt } from '../api'
import { Card, Tile, Callout, PageHead, Num, Tabs, Waveform, BandBars, Heat, Plot, NeedTarget } from '../ui'

export default function TargetPage() {
  const s = useStore()
  const [kind, setKind] = useState('hammer')
  const [level, setLevel] = useState(60)
  const [file, setFile] = useState<File | null>(null)
  const [cal, setCal] = useState({ mode: 'pa_float', value: 94, t0: 0, t1: 1, weighting: 'Z' })
  const [dist, setDist] = useState(7)
  const [recv, setRecv] = useState(7)
  const [atm, setAtm] = useState(true)
  const [temp, setTemp] = useState(20)
  const [rh, setRh] = useState(70)
  const [ev, setEv] = useState<[number, number]>([0, 4])
  const [bg, setBg] = useState<[number, number]>([0, 0.5])
  const [tab, setTab] = useState<'third' | 'a' | 'oct'>('third')
  const t = s.target
  const apply = (x: any) => { s.setTarget(x); if (x?.event) setEv([x.event[0], x.event[1]]) }

  const demo = async () => { const x = await s.run('generating demo', () => api.demo(s.wid!, kind, level, 4)); if (x) apply(x) }
  const upload = async () => {
    if (!file) return
    const f: Record<string, string> = { cal_mode: cal.mode, cal_value: String(cal.value), cal_t0: String(cal.t0), cal_weighting: cal.weighting, distance: String(dist) }
    if (cal.mode !== 'known_level' || true) f.cal_t1 = String(cal.t1)
    const x = await s.run('reading WAV', () => api.uploadTarget(s.wid!, file, f)); if (x) { apply(x); setRecv(dist) }
  }
  const settings = async (body: Record<string, unknown>) => { const x = await s.run('updating', () => api.settings(s.wid!, body)); if (x) apply(x) }
  const bgFile = async (f: File | null) => { if (!f) return; const x = await s.run('background subtraction', () => api.uploadBackground(s.wid!, f)); if (x) apply(x) }

  return (
    <div className="page">
      <PageHead title="Target recording">Load the industrial noise as a pressure signal in pascal at the microphone. Calibrate, re-reference to the receiver distance, remove the background, and choose the event window the models will analyse (max 10 s).</PageHead>
      <div className="grid g12">
        <div className="stack">
          <Card title="Source" sub="A synthetic demo target is provided so every step can be tried at once.">
            <div className="stack">
              <div className="row">
                <div className="field" style={{ flex: 1 }}><label>Synthetic demo</label>
                  <select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(s.presets?.target_kinds || {}).map(([k, l]) => <option key={k} value={k}>{l as string}</option>)}</select></div>
                <Num label="LAeq" unit="dBA" v={level} set={setLevel} />
              </div>
              <button className="btn primary" onClick={demo} disabled={!s.wid}>Generate demo target</button>
              <hr style={{ borderColor: 'var(--line)', width: '100%' }} />
              <div className="field"><label>Upload WAV (mono, any sampling rate, 16/24/32-bit or float)</label><input type="file" accept=".wav,audio/wav" onChange={e => setFile(e.target.files?.[0] || null)} /></div>
              <div className="field"><label>Amplitude calibration</label>
                <select value={cal.mode} onChange={e => setCal({ ...cal, mode: e.target.value })}>
                  <option value="pa_float">Samples are already pascal (Pa)</option>
                  <option value="fullscale_pa">Full scale (±1) = X Pa peak</option>
                  <option value="calibrator">Calibrator tone present in the file</option>
                  <option value="known_level">Known level of a section</option>
                </select></div>
              {cal.mode === 'fullscale_pa' && <Num label="Full scale" unit="Pa peak" v={cal.value} set={v => setCal({ ...cal, value: v })} step={0.1} />}
              {cal.mode === 'calibrator' && <div className="row"><Num label="Calibrator level" unit="dB" v={cal.value} set={v => setCal({ ...cal, value: v })} hint="94 or 114 dB at 1 kHz" /><Num label="from" unit="s" v={cal.t0} set={v => setCal({ ...cal, t0: v })} step={0.1} /><Num label="to" unit="s" v={cal.t1} set={v => setCal({ ...cal, t1: v })} step={0.1} /></div>}
              {cal.mode === 'known_level' && <div className="row"><Num label="Level" unit="dB" v={cal.value} set={v => setCal({ ...cal, value: v })} /><Num label="from" unit="s" v={cal.t0} set={v => setCal({ ...cal, t0: v })} step={0.1} /><Num label="to" unit="s" v={cal.t1} set={v => setCal({ ...cal, t1: v })} step={0.1} />
                <div className="field"><label>Weighting</label><select value={cal.weighting} onChange={e => setCal({ ...cal, weighting: e.target.value })}><option value="Z">Z (flat)</option><option value="A">A</option></select></div></div>}
              <Num label="Microphone distance" unit="m" v={dist} set={setDist} step={0.5} hint="Default 7 m" />
              <button className="btn" onClick={upload} disabled={!file || !s.wid}>Load recording</button>
            </div>
          </Card>

          {t && <Card title="Receiver and background" sub="Physical receiver level ≠ headphone level. Spherical spreading and ISO 9613-1 air absorption only; no ground or barrier effects.">
            <div className="stack">
              <div className="row"><Num label="Receiver distance" unit="m" v={recv} set={setRecv} step={0.5} />
                <label className="row" style={{ marginTop: 18 }}><input type="checkbox" checked={atm} onChange={e => setAtm(e.target.checked)} /> air absorption</label></div>
              <div className="row"><Num label="Temperature" unit="°C" v={temp} set={setTemp} /><Num label="Humidity" unit="% RH" v={rh} set={setRh} /></div>
              <div className="row"><Num label="Event window start" unit="s" v={ev[0]} set={v => setEv([v, ev[1]])} step={0.1} /><Num label="end" unit="s" v={ev[1]} set={v => setEv([ev[0], v])} step={0.1} /></div>
              <button className="btn" onClick={() => settings({ meas_distance: dist, recv_distance: recv, atmosphere: atm, temperature_c: temp, humidity: rh, event: ev })}>Apply distance, air and window</button>
              <hr style={{ borderColor: 'var(--line)', width: '100%' }} />
              <h4>Background subtraction</h4>
              <div className="row"><Num label="Background-only segment from" unit="s" v={bg[0]} set={v => setBg([v, bg[1]])} step={0.1} /><Num label="to" unit="s" v={bg[1]} set={v => setBg([bg[0], v])} step={0.1} /></div>
              <div className="row"><button className="btn sm" onClick={() => settings({ bg_segment: bg })}>Subtract segment</button>
                <button className="btn sm ghost" onClick={() => settings({ bg_clear: true })}>Clear</button></div>
              <div className="field"><label>…or a background WAV</label><input type="file" accept=".wav" onChange={e => bgFile(e.target.files?.[0] || null)} /></div>
            </div>
          </Card>}
        </div>

        <div className="stack">
          {!t ? <NeedTarget /> : <>
            {t.synthetic && <Callout kind="warn"><b>SYNTHETIC target.</b> {t.source.replace(/^SYNTHETIC /, "")}. Use a real calibrated recording for engineering conclusions.</Callout>}
            {t.warnings?.map((w: string, i: number) => <Callout key={i} kind="warn">{w}</Callout>)}
            <div className="grid g4">
              <Tile kind="target" k="LAeq (event)" v={fmt(t.stats.LAeq_event)} u="dBA" d={`Leq ${fmt(t.stats.Leq_event)} dB`} />
              <Tile k="Peak" v={fmt(t.stats.Lpeak)} u="dB" d={`crest ≈ ${fmt(t.stats.Lpeak - t.stats.Leq_event, 0)} dB`} />
              <Tile k="Duration" v={fmt(t.duration_s, 1)} u="s" d={`window ${fmt(t.event[0], 1)}–${fmt(t.event[1], 1)} s`} />
              <Tile k="Calibration" v={t.cal.mode === 'pa_float' ? 'Pa' : fmt(20 * Math.log10(t.cal_gain), 1)} u={t.cal.mode === 'pa_float' ? '' : 'dB gain'} d={`${t.distance.measured} m → ${t.distance.receiver} m`} />
            </div>
            <Card title="Waveform" sub="Min/max envelope of the receiver pressure; the shaded part of the level plot is the analysed window.">
              <Waveform w={t.waveform} />
              <Plot height={150} data={[{ x: t.level_time.t, y: t.level_time.LA, type: 'scatter', mode: 'lines', line: { color: '#E69F00', width: 1.6 }, name: 'LA, 125 ms' }]}
                layout={{ xaxis: { title: { text: 'Time (s)' } }, yaxis: { title: { text: 'dBA (125 ms)' } }, margin: { l: 62, r: 10, t: 6, b: 36 },
                  shapes: [{ type: 'rect', xref: 'x', yref: 'paper', x0: t.event[0], x1: t.event[1], y0: 0, y1: 1, fillcolor: 'rgba(46,196,182,.12)', line: { width: 0 } }] }} />
            </Card>
            <div className="grid g2">
              <Card title="Spectrum of the event" right={<Tabs items={[['third', '1/3 oct'], ['a', '1/3 oct, A'], ['oct', 'Octave']]} v={tab} set={setTab} />}>
                {tab === 'oct' ? <BandBars s={{ third_octave: t.spectra.octave }} /> : <BandBars s={t.spectra} weighted={tab === 'a'} color="#E69F00" />}
              </Card>
              <Card title="Spectrogram" sub="Power per bin, dB re 20 µPa; log frequency.">
                <Heat z={t.spectrogram.L} x={t.spectrogram.t} y={t.spectrogram.f} zmin={Math.max(-10, t.stats.Lpeak - 90)} zmax={t.stats.Lpeak - 25} colorscale="Cividis" height={250} />
              </Card>
            </div>
          </>}
        </div>
      </div>
    </div>
  )
}

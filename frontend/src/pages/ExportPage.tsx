import { useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import { Card, PageHead, NeedTarget, Callout, Slider } from '../ui'

export default function ExportPage() {
  const s = useStore()
  const [idx, setIdx] = useState(0)
  const [snr, setSnr] = useState(-10)
  if (!s.target || !s.wid) return <div className="page"><PageHead title="Reports and exports" /><NeedTarget /></div>
  const w = s.wid
  const dl = (kind: string) => { window.location.href = api.exportUrl(w, kind) }
  const spec = s.specs[idx]
  const mixUrl = `/api/workspace/${w}/audio/mix.wav?masker=${encodeURIComponent(JSON.stringify(spec))}&snr=${snr}&kind=pa`
  const mixUrlN = `/api/workspace/${w}/audio/mix.wav?masker=${encodeURIComponent(JSON.stringify(spec))}&snr=${snr}&kind=norm`
  const have = { predict: !!s.predict, compare: !!s.compare }
  return (
    <div className="page">
      <PageHead title="Reports and exports">Everything is reproducible: the configuration file stores the calibration, distances, scenes (with seeds), criterion and model versions. Results exports contain only what has been computed in this session.</PageHead>
      <div className="grid g2">
        <Card title="Results" sub={`Computed so far: ${have.predict ? 'predictions' : 'no predictions'}, ${have.compare ? 'comparison' : 'no comparison'}.`}>
          <div className="stack">
            <div className="row"><button className="btn primary" onClick={() => dl('pdf')}>PDF report</button><span style={{ color: 'var(--ink-3)' }}>target, detection curves, masker table, listening results, limitations</span></div>
            <div className="row"><button className="btn" onClick={() => dl('xlsx')}>Excel workbook</button><span style={{ color: 'var(--ink-3)' }}>summary, maskers, curves, trials, psychometric, model vs human</span></div>
            <div className="row"><button className="btn" onClick={() => dl('csv')}>CSV (masker comparison)</button></div>
            <div className="row"><button className="btn" onClick={() => dl('config')}>Configuration JSON</button><span style={{ color: 'var(--ink-3)' }}>reproducible settings</span></div>
          </div>
        </Card>
        <Card title="Audio mixtures" sub="Target + masker at physical receiver levels, ready for analysis in other tools.">
          <div className="stack">
            <div className="field"><label>Scene</label><select value={idx} onChange={e => setIdx(+e.target.value)}>{s.specs.map((sp, i) => <option key={i} value={i}>{sp.name}</option>)}</select></div>
            <Slider label="SNR (target LAeq − masker LAeq)" v={snr} set={setSnr} min={-40} max={20} unit="dB" />
            <div className="row"><a className="btn" href={mixUrl} download="mixture_pa.wav">Download WAV, float32 in Pa</a><a className="btn" href={mixUrlN} download="mixture_normalised.wav">Download WAV, normalised 24-bit</a></div>
            <Callout>The float WAV holds pressure in pascal (a measurement-software convention); the normalised WAV is for convenience and loses the absolute level. Neither is calibrated for headphones — use the Listening page for safe presentation.</Callout>
          </div>
        </Card>
      </div>
    </div>
  )
}

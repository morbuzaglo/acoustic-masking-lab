import { ReactNode, useEffect, useRef } from 'react'
// @ts-ignore - plotly dist bundle ships without strict typings for the default export
import Plotly from 'plotly.js-dist-min'
import { useStore } from './store'

export const CAT = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00', '#F0E442', '#9aa5b1', '#882255']
const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

export function Plot({ data, layout, height = 300, onClick }: { data: any[]; layout?: any; height?: number; onClick?: (e: any) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const { theme } = useStore()
  useEffect(() => {
    if (!ref.current) return
    const ink = css('--ink-2'), grid = css('--line'), bg = 'rgba(0,0,0,0)'
    const base = {
      paper_bgcolor: bg, plot_bgcolor: bg, font: { family: 'Inter, system-ui, sans-serif', color: ink, size: 12 },
      margin: { l: 56, r: 16, t: 14, b: 44 }, height, hoverlabel: { font: { family: 'JetBrains Mono, monospace', size: 12 } },
      xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid, ...(layout?.xaxis || {}) },
      yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid, ...(layout?.yaxis || {}) },
      legend: { orientation: 'h', y: -0.22, font: { size: 11 } }, colorway: CAT,
    }
    const merged = { ...base, ...layout, xaxis: { ...base.xaxis, ...(layout?.xaxis || {}) }, yaxis: { ...base.yaxis, ...(layout?.yaxis || {}) }, height }
    Plotly.react(ref.current, data, merged, { displayModeBar: false, responsive: true })
    if (onClick) (ref.current as any).on?.('plotly_click', onClick)
  }, [data, layout, height, theme])
  useEffect(() => { const el = ref.current; return () => { if (el) Plotly.purge(el) } }, [])
  return <div ref={ref} className="plot" style={{ height }} />
}

export function Card({ title, sub, right, children, className = '' }: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && <div className="ch"><h3>{title}</h3>{right}</div>}
      {sub && <div className="sub">{sub}</div>}
      {children}
    </section>
  )
}
export const Tile = ({ k, v, u, d, kind = '' }: { k: string; v: ReactNode; u?: string; d?: ReactNode; kind?: string }) => (
  <div className={`tile ${kind}`}><div className="k">{k}</div><div className="v">{v}{u && <span className="u">{u}</span>}</div>{d && <div className="d">{d}</div>}</div>
)
export const Callout = ({ kind = '', children }: { kind?: string; children: ReactNode }) => <div className={`callout ${kind}`}>{children}</div>
export function Slider({ label, v, set, min, max, step = 1, unit = '', hint, digits = 0 }: { label: string; v: number; set: (n: number) => void; min: number; max: number; step?: number; unit?: string; hint?: string; digits?: number }) {
  return (
    <div className="field">
      <div className="slider-row"><label>{label}</label><span className="val">{v.toFixed(digits)} {unit}</span></div>
      <input type="range" min={min} max={max} step={step} value={v} onChange={e => set(parseFloat(e.target.value))} aria-label={label} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}
export function Num({ label, v, set, step = 1, unit, hint, min, max }: { label: string; v: number; set: (n: number) => void; step?: number; unit?: string; hint?: string; min?: number; max?: number }) {
  return (
    <div className="field"><label>{label}{unit ? ` (${unit})` : ''}</label>
      <input type="number" value={v} step={step} min={min} max={max} onChange={e => set(parseFloat(e.target.value))} />
      {hint && <span className="hint">{hint}</span>}</div>
  )
}
export function Tabs<T extends string>({ items, v, set }: { items: [T, string][]; v: T; set: (t: T) => void }) {
  return <div className="tabs" role="tablist">{items.map(([k, l]) => <button key={k} role="tab" aria-selected={v === k} className={v === k ? 'on' : ''} onClick={() => set(k)}>{l}</button>)}</div>
}
export const Spinner = () => <span className="spinner" role="status" aria-label="working" />
export const PageHead = ({ title, children, right }: { title: string; children?: ReactNode; right?: ReactNode }) => (
  <div className="page-head"><div style={{ flex: 1, minWidth: 260 }}><h1>{title}</h1>{children && <p>{children}</p>}</div>{right}</div>
)
export const NeedTarget = () => <div className="empty"><div><h3>No target loaded yet</h3><p>Go to <b>1 · Target</b> and load the demo or upload a calibrated WAV.</p></div></div>

export function Heat({ z, x, y, title, zmin, zmax, ylog = true, colorscale = 'Viridis', height = 320, ytitle = 'Frequency (Hz)', xtitle = 'Time (s)', cbtitle = 'dB', ticks }:
  { ticks?: { vals: number[]; text: string[] }; z: number[][]; x: number[]; y: number[]; title?: string; zmin?: number; zmax?: number; ylog?: boolean; colorscale?: string; height?: number; ytitle?: string; xtitle?: string; cbtitle?: string }) {
  return <Plot height={height} data={[{ type: 'heatmap', z, x, y, zmin, zmax, colorscale, zsmooth: false, colorbar: { title: { text: cbtitle, side: 'right' }, thickness: 12, len: 0.9 },
    hovertemplate: 't=%{x:.2f} s<br>f=%{y:.0f} Hz<br>%{z:.1f} dB<extra></extra>' }]}
    layout={{ xaxis: { title: { text: xtitle } }, yaxis: { title: { text: ytitle }, type: ylog ? 'log' : 'linear', ...(ticks ? { tickmode: 'array', tickvals: ticks.vals, ticktext: ticks.text } : {}) }, margin: { l: 62, r: 10, t: 8, b: 44 }, title: title ? { text: title, font: { size: 13 } } : undefined }} />
}
export function Waveform({ w, color = '#E69F00', height = 190 }: { w: { t: number[]; lo: number[]; hi: number[] }; color?: string; height?: number }) {
  const xs = [...w.t, ...[...w.t].reverse()]
  const ys = [...w.hi, ...[...w.lo].reverse()]
  return <Plot height={height} data={[{ x: xs, y: ys, type: 'scatter', mode: 'lines', fill: 'toself', line: { width: 0.5, color }, fillcolor: color + '99', hoverinfo: 'skip', showlegend: false }]}
    layout={{ xaxis: { title: { text: 'Time (s)' } }, yaxis: { title: { text: 'Pressure (Pa)' } }, margin: { l: 62, r: 10, t: 8, b: 40 } }} />
}
export function BandBars({ s, color = '#4fb0e8', weighted = false, extra = [], height = 250 }: { s: any; color?: string; weighted?: boolean; extra?: any[]; height?: number }) {
  const y = weighted ? s.third_octave.LA : s.third_octave.L
  return <Plot height={height} data={[{ type: 'bar', x: s.third_octave.fc.map((f: number) => String(f)), y, marker: { color }, name: weighted ? 'LA' : 'L', hovertemplate: '%{x} Hz: %{y:.1f} dB<extra></extra>' }, ...extra]}
    layout={{ xaxis: { title: { text: '1/3-octave band centre (Hz)' }, type: 'category', tickangle: -60, tickfont: { size: 10 } }, yaxis: { title: { text: weighted ? 'dBA' : 'dB re 20 µPa' }, rangemode: 'normal' }, bargap: 0.15, margin: { l: 56, r: 10, t: 8, b: 66 } }} />
}
export const Swatch = ({ c }: { c: string }) => <span className="swatch" style={{ background: c }} />

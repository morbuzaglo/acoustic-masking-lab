import { useState } from 'react'
import { useStore } from './store'
import { Spinner } from './ui'
import Overview from './pages/Overview'
import ProjectsPage from './pages/ProjectsPage'
import TargetPage from './pages/TargetPage'
import MaskersPage from './pages/MaskersPage'
import PredictPage from './pages/PredictPage'
import OptimizePage from './pages/OptimizePage'
import CaspPage from './pages/CaspPage'
import ListenPage from './pages/ListenPage'
import ExportPage from './pages/ExportPage'
import MethodPage from './pages/MethodPage'

const PAGES = [
  ['overview', 'Overview', Overview], ['projects', 'Projects', ProjectsPage], ['target', 'Target', TargetPage], ['maskers', 'Maskers', MaskersPage],
  ['predict', 'Predict', PredictPage], ['optimize', 'Optimise', OptimizePage], ['casp', 'CASP check', CaspPage],
  ['listen', 'Listening test', ListenPage], ['export', 'Reports', ExportPage], ['method', 'Method & limits', MethodPage],
] as const

export default function App() {
  const [page, setPage] = useState<string>(() => location.hash.slice(1) || 'overview')
  const s = useStore()
  const go = (p: string) => { setPage(p); location.hash = p; document.querySelector('.main')?.scrollTo({ top: 0 }) }
  const Cur = (PAGES.find(p => p[0] === page) || PAGES[0])[2]
  const done: Record<string, boolean> = { target: !!s.target, predict: !!s.predict, optimize: !!s.compare, casp: !!s.casp }
  return (
    <div className="app">
      <nav className="side" aria-label="Main">
        <div className="brand">
          <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="8" fill="#0E1620" stroke="#223446" /><path d="M4 16h3l3-8 4 16 4-12 3 4h7" fill="none" stroke="#2EC4B6" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <div><b>Acoustic Masking Lab</b><small>detectability · 2AFC · CASP</small></div>
        </div>
        {PAGES.map(([k, l], i) => (
          <button key={k} className={`nav ${page === k ? 'active' : ''} ${done[k] ? 'done' : ''}`} onClick={() => go(k)} aria-current={page === k ? 'page' : undefined}>
            <span className="step">{done[k] ? '✓' : i}</span>{l}
          </button>
        ))}
        <div className="spacer" />
        <button className="nav" onClick={s.toggleTheme}><span className="step">{s.theme === 'dark' ? '☾' : '☀'}</span>{s.theme === 'dark' ? 'Dark' : 'Light'} theme</button>
      </nav>
      <div className="main">
        <header className="top">
          <span className="title">{PAGES.find(p => p[0] === page)?.[1]}</span>
          {s.busy && <span className="chip"><Spinner /> {s.busy}…</span>}
          <div className="chips">
            <span className={`chip ${s.projectId ? 'ok' : ''}`}><i />{s.projectName}{s.projectId ? '' : ' (unsaved)'}</span>
            <span className={`chip ${s.target ? 'ok' : 'warn'}`}><i />{s.target ? (s.target.synthetic ? 'synthetic target' : 'target loaded') : 'no target'}</span>
            <span className={`chip ${!s.health ? '' : s.health.casp?.available ? 'ok' : 'warn'}`}><i />CASP {!s.health ? 'checking' : s.health.casp?.available ? 'available' : 'unavailable'}</span>
            <span className="chip"><i />P<sub>crit</sub> {s.pCrit.toFixed(2)}</span>
            {s.offsetDb !== 0 && <span className="chip ok"><i />participant {s.offsetDb > 0 ? '+' : ''}{s.offsetDb.toFixed(1)} dB</span>}
          </div>
        </header>
        <Cur go={go} />
        {s.msg && <div className="toast" role="alert">{s.msg}</div>}
      </div>
    </div>
  )
}

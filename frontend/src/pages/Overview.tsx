import { useStore } from '../store'
import { api } from '../api'
import { Card, Callout } from '../ui'

export default function Overview({ go }: { go: (p: string) => void }) {
  const s = useStore()
  const loadDemo = async () => {
    if (!s.wid) return
    const t = await s.run('loading demo', () => api.demo(s.wid!, 'hammer', 60, 4))
    if (t) { s.setTarget(t); go('target') }
  }
  return (
    <div className="page">
      <div className="hero">
        <h1>Will they hear the drilling through the birdsong?</h1>
        <p>Acoustic Masking Lab predicts whether industrial noise stays perceptually detectable when it is mixed with a natural or synthetic background, finds the <b>smallest masker</b> that reaches a detectability target, and lets you check the prediction with <b>blinded listening tests</b>. Predictions come from psychoacoustic models (ERB filterbank, temporal masking, signal detection theory, and the CASP model from the Auditory Modeling Toolbox) and always carry an uncertainty.</p>
        <div className="row">
          <button className="btn primary big" onClick={loadDemo} disabled={!s.wid}>Start with the demo (synthetic hammering)</button>
          <button className="btn big" onClick={() => go('target')}>Use my own recording</button>
        </div>
      </div>

      <div className="grid" style={{ marginTop: 18 }}>
        <Card title="The workflow" sub="Every step is a page in the sidebar. Receiver levels are physical; headphone levels are separate.">
          <div className="pipe">
            <div className="node"><b>1 · Target</b><span>WAV in Pa, calibration, distance, background removal</span></div>
            <div className="node"><b>2 · Maskers</b><span>Wind, water, rain, leaves, crickets, noise colours, your WAVs</span></div>
            <div className="node"><b>3 · Predict</b><span>P(detect) versus masker level, masking maps, uncertainty</span></div>
            <div className="node"><b>4 · Optimise</b><span>Lowest extra dBA and annoyance proxy for a chosen detectability</span></div>
            <div className="node"><b>5 · Listen</b><span>Blinded 2AFC, staircase, psychometric fit, model vs human</span></div>
          </div>
        </Card>

        <div>
          <h4 style={{ margin: '6px 0 10px' }}>Four different things this tool keeps apart</h4>
          <div className="cons">
            <Card title="Energetic masking"><p>The masker’s energy in the same auditory filter and time window hides the target. This is what the models here predict.</p></Card>
            <Card title="Detectability"><p>Whether a listener can tell the target is present (2AFC proportion correct, d′). Not the same as whether it is noticed in daily life.</p></Card>
            <Card title="Attentional distraction"><p>Salient sounds (barking, a hammer) capture attention even when masked. Not predicted; only listening tests with realistic tasks can address it.</p></Card>
            <Card title="Annoyance"><p>A judgement of unpleasantness. A masker adds sound; it can reduce detectability and still raise annoyance. Reported separately as a proxy.</p></Card>
          </div>
        </div>

        <Callout kind="warn"><b>Masking never removes noise; it adds sound.</b> Results are model predictions for normal-hearing listeners with their uncertainty, not a guarantee of inaudibility. Synthetic targets and maskers are labelled SYNTHETIC and are no substitute for calibrated field recordings.</Callout>
      </div>
    </div>
  )
}

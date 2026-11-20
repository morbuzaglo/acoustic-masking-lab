import { Card, PageHead, Callout } from '../ui'

const REFS: [string, string, string][] = [
  ['Paulick, Relaño-Iborra & Dau (2024). The Computational Auditory Signal Processing and Perception Model (CASP): A Revised Version. bioRxiv preprint.', '10.1101/2024.07.31.605576', 'preprint'],
  ['Jepsen, Ewert & Dau (2008). A computational model of human auditory signal processing and perception. J. Acoust. Soc. Am. 124(1), 422–438.', '10.1121/1.2924135', ''],
  ['Majdak, Hollomey & Baumgartner (2022). AMT 1.x: A toolbox for reproducible research in auditory modeling. Acta Acustica 6, 19.', '10.1051/aacus/2022011', ''],
  ['Dau, Kollmeier & Kohlrausch (1997). Modeling auditory processing of amplitude modulation. I. Detection and masking with narrow-band carriers. J. Acoust. Soc. Am. 102(5), 2892–2905.', '', 'DOI not verified'],
  ['Ewert & Dau (2000). Characterizing frequency selectivity for envelope fluctuations. J. Acoust. Soc. Am. 108(3), 1181–1196.', '10.1121/1.1288665', 'DOI from one source'],
  ['Glasberg & Moore (1990). Derivation of auditory filter shapes from notched-noise data. Hearing Research 47(1–2), 103–138.', '', ''],
  ['Moore, Glasberg & Baer (1997). A model for the prediction of thresholds, loudness, and partial loudness. J. Audio Eng. Soc. 45(4), 224–240.', '', ''],
  ['Hohmann (2002). Frequency analysis and synthesis using a Gammatone filterbank. Acta Acustica united with Acustica 88, 433–442.', '', ''],
  ['Hawkins & Stevens (1950). The masking of pure tones and of speech by white noise. J. Acoust. Soc. Am. 22(1), 6–13.', '', 'DOI not verified'],
  ['Jesteadt, Bacon & Lehman (1982). Forward masking as a function of frequency, masker level, and signal delay. J. Acoust. Soc. Am. 71(4), 950–962.', '10.1121/1.387576', ''],
  ['Plomp & Bouman (1959). Relation between hearing threshold and duration for tone pulses. J. Acoust. Soc. Am. 31(6), 749–758.', '10.1121/1.1907781', ''],
  ['Terhardt (1979). Calculating virtual pitch. Hearing Research 1, 155–182 (the threshold-in-quiet approximation is quoted from secondary sources, not checked against this paper).', '', ''],
  ['Fastl & Zwicker (2007). Psychoacoustics: Facts and Models, 3rd ed. Springer.', '10.1007/978-3-540-68888-4', ''],
  ['Durlach, Mason, Kidd, Arbogast, Colburn & Shinn-Cunningham (2003). Note on informational masking. J. Acoust. Soc. Am. 113(6), 2984–2987.', '10.1121/1.1570435', ''],
  ['Levitt (1971). Transformed up-down methods in psychoacoustics. J. Acoust. Soc. Am. 49(2B), 467–477.', '10.1121/1.1912375', ''],
  ['Wichmann & Hill (2001). The psychometric function: I. Fitting, sampling, and goodness of fit. Perception & Psychophysics 63, 1293–1313.', '10.3758/BF03194544', ''],
  ['Hong, Ong, Lam, Ooi, Gan, Kang, Feng & Tan (2020). Effects of adding natural sounds to urban noises on the perceived loudness of noise and soundscape quality. Sci. Total Environ. 711, 134571 (hydraulic breaker and traffic noise with birdsong and stream sounds).', '10.1016/j.scitotenv.2019.134571', ''],
  ['Jeon, Lee, You & Kang (2010). Perceptual assessment of quality of urban soundscapes with combined noise sources and water sounds. J. Acoust. Soc. Am. 127(3), 1357–1366.', '10.1121/1.3298437', ''],
]

export default function MethodPage() {
  return (
    <div className="page">
      <PageHead title="Method, assumptions and limits">What the models do, what they were checked against, and where not to use them.</PageHead>
      <div className="grid g2">
        <Card title="Fast model: ERB-EDM">
          <div className="stack">
            <p>An ERB-spaced gammatone filterbank (36 channels, 50–12000 Hz) gives the excitation of target and masker in 10 ms+ windows. The masker excitation is extended by forward masking (τ = 30 ms) and floored by the absolute threshold in quiet. In every time–frequency cell an energy detector sees the target as a relative change of the masker energy with fluctuation 1/(T·W) plus a 0.1 level-resolution floor. Cells are combined optimally over channels and a 300 ms integration window.</p>
            <div className="formula">d′² = max<sub>t</sub> Σ<sub>k,cells∈window</sub> (η · E<sub>T</sub> / (E<sub>M</sub> + E<sub>int</sub>))² / (1/(T<sub>k</sub>W<sub>k</sub>) + ε²) · (hop / T<sub>k</sub>)</div>
            <div className="formula">P<sub>2AFC</sub> = Φ(d′ / √2)</div>
            <p>η is calibrated once so that a 500 ms 1 kHz tone in white noise reaches P = 0.75 at a critical ratio of 18 dB. The model then reproduces the rise of the critical ratio with frequency (15 → 25 dB from 250 Hz to 8 kHz) and the 10 dB-per-decade temporal integration trend in the automated tests.</p>
          </div>
        </Card>
        <Card title="Reference model: CASP via AMT 1.6.0">
          <div className="stack">
            <p>MATLAB runs the AMT function <code>paulick2024</code> unmodified (outer/middle ear, 50-channel DRNL, hair-cell stage, adaptation loops, modulation filterbank), and the AMT correlation and decision stages. The AMT back end was published for intensity discrimination. For noise maskers the decision variance had to be re-calibrated (σ² = 619 instead of 40, anchored to the same critical ratio), which is documented in the CASP page and the validation files. The tool never presents CASP numbers produced by anything other than that code.</p>
            <Callout kind="warn"><b>Observed disagreement.</b> At 4 kHz the calibrated CASP threshold is about 4.7 dB lower (more sensitive) than the fast model, and the CASP psychometric function is shallower. The fast model’s documented ±3 dB model-form uncertainty is therefore somewhat optimistic; use both models and listening tests.</Callout>
          </div>
        </Card>
        <Card title="What is and is not predicted">
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li><b>Energetic masking and detectability</b> of a known target in a given masker, for a normal-hearing listener at moderate levels.</li>
            <li><b>Not predicted:</b> informational masking and uncertainty effects (Durlach et al. 2003), attention capture, cognitive effects, audio-visual interaction, or long-term annoyance.</li>
            <li><b>Annoyance proxies</b> (N5, sharpness, fluctuation, PA) are relative engineering indicators built on the model excitation, calibrated to the reference stimuli (1 sone, 1 acum, 1 vacil); they are not ISO 532 or standardised PA values.</li>
            <li>Maskers add sound. A masker that lowers detectability can still increase annoyance, especially if it is itself salient (Hong et al. 2020; Jeon et al. 2010 on level and soundscape quality).</li>
            <li>Impulsive industrial noise is the hard case: with a high crest factor the required masker level follows the <i>peaks</i>, not the LAeq, so LAeq-based reasoning underestimates it.</li>
          </ul>
        </Card>
        <Card title="Levels and safety">
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)' }}>
            <li><b>Receiver SPL</b> is the physical level at the listener's position; the target is re-referenced from the microphone distance by spherical spreading and ISO 9613-1 air absorption. Ground, barriers and weather are not modelled.</li>
            <li><b>Headphone level</b> is separate: it needs the measured sensitivity (dB SPL of a full-scale sine). Without it the test is run at nominal, uncalibrated levels, labelled as such.</li>
            <li>Playback is capped (default 70 dBA, hard limit 85 dBA); target and masker are scaled together so the SNR is preserved.</li>
          </ul>
        </Card>
      </div>
      <Card title="References (verified online unless marked)" className="">
        <ol style={{ margin: 0, paddingLeft: 20, color: 'var(--ink-2)', display: 'grid', gap: 6 }}>
          {REFS.map(([t, doi, note], i) => <li key={i}>{t} {doi && <>DOI <a href={`https://doi.org/${doi}`} target="_blank" rel="noreferrer">{doi}</a>. </>}{note && <span className="tag">{note}</span>}</li>)}
        </ol>
      </Card>
    </div>
  )
}

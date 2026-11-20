# Research review: detectability of industrial noise in natural maskers

Verified 2026-11-20 by web search of bibliographic records. "Verified" means title, authors, venue, pages and (where given) DOI were found in at least one record; full texts were generally **not** read, and claims below rest on abstracts or on the code itself where stated. Items marked (?) were not fully verified.

## 1. Models used or considered

| Model | What it predicts | Key assumptions | Applicability limits | Used here |
|---|---|---|---|---|
| **CASP / Paulick2024** (AMT 1.6.0 `paulick2024`) [1][2][3] | Detection from an internal representation after outer/middle ear, DRNL filterbank, hair-cell stage, adaptation loops, modulation filterbank | Normal-hearing listener, correlation with a template, internal noise | AMT ships only the intensity-discrimination back end; seconds per stimulus; absolute-level dependent | Yes, MATLAB bridge; front end unmodified, noise-masker decision variance re-calibrated |
| **Jepsen 2008 CASP** [2] | Same family, linear gammatone front end | Same | Superseded by [1]; implementation "as close as possible" per AMT code comments | Available as `model='jepsen2008'` in the bridge, not used in studies |
| **Dau 1997 modulation filterbank model** [4], **EPSM** [5] | Modulation detection and masking | Envelope processing in modulation filters | Modulation-specific | Background only; modulation is explicit only inside CASP |
| **ERB excitation / loudness** [6][7] | Excitation patterns, thresholds, partial loudness | Auditory filter shapes from notched-noise data | Steady sounds | ERB scale used; no Moore-Glasberg loudness implemented (proxy only) |
| **Gammatone filterbank** [8][19] | Basilar-membrane filtering | 4th order, ERB bandwidth | Linear, level independent | ERB-EDM (complex 4-pole cascade after Hohmann) |
| **Signal detection theory, 2AFC** [27] | P(correct) = Phi(d'/sqrt 2) | Equal variance, independent intervals | Ideal-observer mapping | Both models |

## 2. Empirical anchors

* Critical ratio of a tone in white noise at 1 kHz is about 18 dB (power ratio to noise spectral density) [9] (DOI not verified). The fast model is calibrated to this single anchor.
* Forward masking decays with signal delay and increases with masker level [10]. Temporal integration of thresholds with duration [11].
* Threshold in quiet approximation [12] (quoted from secondary sources).
* Staircase rules converge to 70.7 % (2-down/1-up) and 79.4 % (3-down/1-up) [15]; psychometric fitting with bootstrap CIs [16].

## 3. Natural-sound masking of industrial noise (empirical literature)

* Hong et al. 2020 [17]: laboratory study adding birdsong or stream sounds to hydraulic-breaker and traffic noise at 55/65/75 dB(A); reports reduced **perceived loudness** and soundscape quality effects. It does not measure detection thresholds.
* Jeon et al. 2010 [18]: water sounds best for urban soundscape quality; level similar to or not less than 3 dB below the noise level (abstract-level reading).
* Smyrnova and Brown 2021 [28]: audio-visual interaction in industrial soundscapes (found by search, not read).
* Informational masking and its definition: Durlach et al. 2003 [14]. Not modelled here.

**Gap addressed by this project:** the literature found supports annoyance/loudness benefits of natural maskers; it does not provide detection thresholds for industrial noise in natural maskers. This tool predicts them and provides an experimental path to measure them.

## 4. Findings from this project that bear on the literature

* For impulsive targets the required masker level follows the peaks, not LAeq (synthetic hammer, crest factor 28 dB: pink noise needed 88 dBA for P <= 0.6).
* Narrow-band or high-frequency-only maskers (rain, leaves, crickets) cannot mask a target with low-frequency components at any level tested (to 80 dB above nominal).
* Natural maskers need very large levels unless their spectrum is reshaped toward the target; after optimisation the required levels converge (85.5-86.6 dBA) but the reshaped sounds are far from natural.
* Fast model vs calibrated CASP differ by 4.7 dB at 4 kHz and have different psychometric slopes.

## 5. Limitations of this review

No peer-reviewed study of CASP applied to noise-masked detection of industrial noise was found; the Paulick et al. preprint [1] was not read in full. Items not verified: DOI of [4] and [9]; [5] DOI from a single record.

Numbering follows `docs/word/refs_aml.py` (the same list appears in the Word summary and in the app's *Method & limits* page).

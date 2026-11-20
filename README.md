# Acoustic Masking Lab

Web application for predicting and experimentally testing whether **industrial noise** (drilling, hammering, impacts) is perceptually **detectable** when mixed with natural or synthetic background sounds. Local, offline, Windows.

* **Predict**: fast ERB excitation + energy-detector model (ERB-EDM, Python) and the real **CASP / Paulick2024** model from the Auditory Modeling Toolbox 1.6.0 (MATLAB).
* **Optimise**: minimum masker level for a detectability target with uncertainty; spectral shaping that minimises added dBA plus a loudness proxy; natural vs synthetic comparison.
* **Listen**: calibrated, safe headphone playback; blinded 2AFC; adaptive staircase (2-down/1-up, 3-down/1-up) or constant stimuli; psychometric fit; model vs human; participant offset.
* **Report**: PDF, Excel, CSV, WAV mixtures, reproducible configuration.

Detectability (energetic masking) is kept separate from attention capture, informational masking and annoyance. See the in-app page *Method & limits* and `docs/`.

## Setup (Windows)

Requirements: Python 3.10+, Node 18+ (for building the UI once), MATLAB R2021b+ with Signal Processing and Statistics toolboxes (only for the CASP page).

```bat
start.bat
```

`start.bat` creates the virtual environment in `%LOCALAPPDATA%\AcousticMaskingLab\venv` (not in OneDrive), builds `frontend/dist` if missing, and starts the server at http://127.0.0.1:8770.

CASP: `start.bat` downloads and unpacks AMT 1.6.0 automatically (`scripts/install_amt.py`, SHA-256 checked, about 14 MB) into `%LOCALAPPDATA%\AcousticMaskingLab\amt`. AMT is not stored in this repository because it is a separate GPL v3+ package with bundled third-party toolboxes (see `THIRD_PARTY_NOTICES.md`). Override locations with `AML_AMT_ROOT` and `AML_MATLAB`. Without MATLAB the CASP page is disabled and everything else works.

Development: `cd frontend && npm run dev` (Vite on :5173, proxies `/api` to :8770); `cd frontend && npx tsc --noEmit && npx vite build`.

## Projects and scene library

* **Projects page**: save/load a whole project (target audio, calibration, distances, window, scenes, criterion, participant offset, headphone settings, last results) to `data/projects/`, download it as one `.amlproj` file, import it elsewhere.
* **Scene library** (`data/library/`): every scene you create or edit, and every masker WAV you upload, is saved automatically and appears in all later projects. Editing a factory scene stores a personal override (the factory version is kept).
* **Optimised shapes** can be saved as scenes and verified in CASP.

## Tests

```bat
%LOCALAPPDATA%\AcousticMaskingLab\venv\Scripts\python.exe -m pytest -q backend\tests
```

32 tests (about 3 min): units and IEC 61672 A-weighting, ISO 9613-1 absorption against ISO 9613-2 Table 2, calibration modes, 1/3-octave sums, generators (level, determinism, spectral slopes), fast-model anchor and trends (critical ratio vs frequency, temporal integration, forward masking, threshold in quiet), staircase convergence, psychometric fit recovery, optimiser constraint, loudness reference points, and the complete HTTP workflow including blinded 2AFC, exports and the safety cap.
CASP validation (MATLAB, ~40 min): `python backend/tests/casp_validation_suite.py` (results in `docs/validation/`).

## Workflow

1. **Target**: upload WAV (Pa, or full-scale/calibrator/known-level calibration), distance (default 7 m), receiver distance, background subtraction, event window. Or generate a SYNTHETIC demo.
2. **Maskers**: wind, crickets, flowing water, rain, leaves, white/pink/brown noise, uploaded WAVs; EQ, tilt, level fluctuation, modulation.
3. **Predict**: P(2AFC) versus masker level and SNR, masking map (ERB x time), required level with 95 % model range.
4. **Optimise**: compare scenes; optimise the spectral shape.
5. **CASP check**: reference model on the scenario (minutes).
6. **Listening test**: set headphone calibration and safety cap, run a staircase, compare with the model, apply the participant offset.
7. **Reports**: PDF / Excel / CSV / config / WAV.

## Layout

```
backend/aml/      units, audio_io, spectra, generators, fastmodel, loudness, optimize, experiments, casp_bridge, reports, service
backend/app.py    FastAPI (also serves frontend/dist)
matlab/casp_run.m  CASP job (AMT paulick2024)
frontend/src      React + TypeScript + Plotly UI
docs/             research review, validation results, Hebrew Word summary
```

## Honest limitations

* The fast model is calibrated to one anchor (critical ratio 18 dB at 1 kHz); against CASP it differs by ~5 dB at 4 kHz and has a steeper psychometric function. Its stated +-3 dB model uncertainty is optimistic.
* AMT 1.6.0 ships the CASP back end for intensity discrimination only; for noise maskers the decision variance is re-calibrated (619 instead of 40) with the same anchor. The front end is unmodified. Raw and calibrated results are both shown.
* Loudness, sharpness, fluctuation and PA are proxies, not ISO 532 values.
* Receiver propagation covers spherical spreading and air absorption only.
* Headphone presentation assumes the entered sensitivity; free-field-to-headphone transfer is not compensated.
* Synthetic maskers/targets are signal models, labelled SYNTHETIC. No field recordings or human data were collected in this project; the listening test machinery was verified with simulated listeners.

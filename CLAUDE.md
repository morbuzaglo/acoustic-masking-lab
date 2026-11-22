# CLAUDE.md

Acoustic Masking Lab: local web app (FastAPI + React/Plotly) that predicts whether industrial noise stays detectable in natural/synthetic maskers, finds the minimum masker level, runs blinded 2AFC listening tests and compares them with models. Read `README.md` first.

## Commands (Windows)
```bat
start.bat                                                                 :: setup + run on http://127.0.0.1:8770
%LOCALAPPDATA%\AcousticMaskingLab\venv\Scripts\python.exe -m pytest -q backend\tests      :: 32 tests, ~2-6 min (single test: append `-k round_trip`)
%LOCALAPPDATA%\AcousticMaskingLab\venv\Scripts\python.exe backend\tests\casp_validation_suite.py   :: MATLAB CASP validation, ~40 min
%LOCALAPPDATA%\AcousticMaskingLab\venv\Scripts\python.exe backend\tests\model_validation.py        :: scenario study + simulated listener
cd frontend && npx tsc --noEmit && npx vite build                          :: UI build into frontend/dist (served by FastAPI)
```
Node is at `C:\Program Files\nodejs` (may be missing from the Bash PATH). `frontend/node_modules` is a **junction** to `%LOCALAPPDATA%\AcousticMaskingLab\fe_node_modules` (OneDrive must not sync it; a sync of thousands of files starved the machine and froze the browser tests). AMT 1.6.0 is not in the repo (GPL, bundled toolboxes, see `THIRD_PARTY_NOTICES.md`): `scripts/install_amt.py` (run by `start.bat`) downloads it to `%LOCALAPPDATA%\AcousticMaskingLab\amt\amtoolbox-1.6.0` (override with `AML_AMT_ROOT`, `AML_MATLAB`). CASP runs through `matlab -batch` subprocesses, not matlabengine.

## Architecture
`backend/aml/`: units, audio_io (calibration, background subtraction), spectra, generators (maskers + SYNTHETIC targets), fastmodel (ERB-EDM), loudness (proxies), optimize (band-gain optimiser), experiments (2AFC), casp_bridge + `matlab/casp_run.m` (real CASP), reports, service. `backend/app.py` is the thin HTTP layer. UI pages in `frontend/src/pages`.
`service.Workspace` holds one project's calibrated target and renders maskers; `projects.py` persists projects (`.amlproj` = project.json + arrays.npz) and the scene library (autosaved scenes + uploaded masker audio) under `data/` (gitignored, `AML_DATA_DIR` overrides; tests use a temp dir). Presets = factory scenes overridden/extended by the library. The frontend store autosaves scenes to the library. Hebrew Word summary: `docs/word/build_word.py` (needs the AcousticBook venv and its `docbuilder`).

## Rules that must survive changes
- Never present fast-model numbers as CASP. CASP = unmodified AMT `paulick2024` front end; the noise-masker decision variance is **re-calibrated** (docs/validation/casp_calibration.json); show raw and calibrated.
- Masking adds sound. Report detectability, dBA added and annoyance proxies separately; no "guaranteed inaudible".
- Receiver SPL (physical) is never mixed with headphone level. Playback cap defaults 75 dBA, **hard cap 85 dBA** (`experiments.HARD_CAP_DBA`), tested.
- Answer keys stay on the server (blinded 2AFC).
- Synthetic targets/maskers are labelled SYNTHETIC. No human data exist; the listening machinery was validated with simulated listeners only.
- Plotly pitfalls: keep heatmaps on small grids; screenshots of the browser tool fail when the machine is overloaded (OneDrive/Defender/Zoom), not because of the app.
- `fastmodel.channel_power` is the hot path (frequency-domain gammatone cascade, `scipy.fft.next_fast_len`); keep the 4-pole complex cascade equivalence (eta calibration depends on it).

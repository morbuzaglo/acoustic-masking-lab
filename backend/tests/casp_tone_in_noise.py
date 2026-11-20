"""Validation run: 1 kHz tone in white noise, CASP (AMT paulick2024) vs the fast ERB-EDM model.
Writes docs/validation/casp_tone_in_noise.json. Takes several minutes (MATLAB)."""
import sys, json, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from aml import casp_bridge as CB, fastmodel as F, units as U
fs = 44100; dur = 0.5; n = int(dur * fs); t = np.arange(n) / fs
N0_db = 20.0                     # dB re (20 uPa)^2/Hz, one-sided
N0 = U.P0**2 * 10**(N0_db/10)
def noise(seed): return np.random.default_rng(seed).standard_normal(n) * np.sqrt(N0 * fs / 2)
env = np.ones(n); nr = int(.02*fs); env[:nr]=np.linspace(0,1,nr); env[-nr:]=np.linspace(1,0,nr)
Ltone = N0_db + 18.0              # tone SPL at the nominal critical ratio
tone = env*np.sin(2*np.pi*1000*t) * np.sqrt(2) * U.P0 * 10**(Ltone/20)
gm = [-6, 0, 6, 12, 18, 24]
R = 5
maskers = [[noise(100+r) for r in range(R)]]
# fast model on the same stimuli (several noise draws)
Pf = []
for g in gm:
    ps = [F.analyse(tone, maskers[0][r], fs).p2afc(0.0, g) for r in range(R)]
    Pf.append(float(np.mean(ps)))
run = CB.CaspRun(); run.start(tone, maskers, fs, gm, ["white noise"], sup_db=6.0)
while run.state == "running":
    time.sleep(5); print(run.info(), flush=True)
if run.state != "done":
    print(run.error); sys.exit(1)
res = run.result
P = np.array(res["P2AFC"]).ravel().tolist()
out = {"scenario": "1 kHz, 500 ms tone, white noise N0=%.0f dB; tone SPL %.1f dB (CR 18 dB)" % (N0_db, Ltone),
       "gm_db": gm, "casp_P2AFC": P, "fast_P2AFC": Pf, "casp_threshold_gm_db": CB.interpolate_threshold(gm, P, .75),
       "fast_threshold_gm_db": CB.interpolate_threshold(gm, Pf, .75), "elapsed_s": res["elapsed_s"]}
pathlib.Path(__file__).resolve().parents[2].joinpath("docs/validation/casp_tone_in_noise.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))

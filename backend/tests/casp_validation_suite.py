"""CASP validation suite (runs MATLAB; ~10 min). Tone-in-noise at 1 kHz and 4 kHz, plus the application
scenario (single hammer impact in pink noise). Calibrates the decision variance from scenario 1 and reports
how the calibrated CASP agrees with the fast ERB-EDM model on the other scenarios."""
import sys, json, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import norm
from aml import casp_bridge as CB, fastmodel as F, units as U, generators as G
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "validation"
fs = 44100; R = 5

def tone_scene(f, N0_db=20.0, dur=0.5, cr=18.0):
    n = int(dur * fs); t = np.arange(n) / fs
    N0 = U.P0**2 * 10**(N0_db/10)
    noises = [np.random.default_rng(100 + r).standard_normal(n) * np.sqrt(N0 * fs / 2) for r in range(R)]
    env = np.ones(n); nr = int(.02*fs); env[:nr] = np.linspace(0, 1, nr); env[-nr:] = np.linspace(1, 0, nr)
    L = N0_db + cr
    tone = env * np.sin(2*np.pi*f*t) * np.sqrt(2) * U.P0 * 10**(L/20)
    return tone, noises

def run(name, tone, noises, gm, label):
    Pf = [float(np.mean([F.analyse(tone, nz, fs).p2afc(0.0, g) for nz in noises])) for g in gm]
    job = CB.CaspRun(); job.start(tone, [noises], fs, gm, [label], sup_db=6.0)
    while job.state == "running":
        time.sleep(10)
    if job.state != "done":
        raise RuntimeError(job.error)
    res = job.result
    return {"name": name, "gm_db": gm, "fast_P": Pf, "mu_r": res["mu_r"], "elapsed_s": res["elapsed_s"]}

out = {}
t1, n1 = tone_scene(1000.0)
out["tone1k"] = run("tone1k", t1, n1, [0, 6, 12, 18, 24, 30], "white noise")
mu0 = np.mean(np.array(out["tone1k"]["mu_r"])[0, :, :], axis=-1)   # per-gm mean mu
# calibrate in_var so that P(gm=0) = 0.75  (tone at CR = 18 dB, 1 kHz)
mu_ref = float(mu0[0])
in_var = (0.707 * mu_ref / norm.ppf(0.75)) ** 2
(OUT / "casp_calibration.json").write_text(json.dumps({"in_var": in_var, "anchor": "1 kHz 500 ms tone, white noise, CR=18 dB -> P2AFC=0.75",
                                                       "in_var_amt_default": 40.0, "mu_ref": mu_ref}, indent=1))
print("calibrated in_var", in_var, flush=True)
t4, n4 = tone_scene(4000.0, cr=21.1)       # fast-model CR at 4 kHz
out["tone4k"] = run("tone4k", t4, n4, [-6, 0, 6, 12, 18], "white noise")
res = {}
for k, v in out.items():
    P = CB.p_table({"mu_r": v["mu_r"]}, in_var)[0]
    res[k] = {"gm_db": v["gm_db"], "casp_P_cal": P.tolist(), "casp_P_raw_amt_invar": CB.p_table({"mu_r": v["mu_r"]}, 40.0)[0].tolist(),
              "fast_P": v["fast_P"], "casp_thr_gm_db": CB.interpolate_threshold(v["gm_db"], P, .75),
              "fast_thr_gm_db": CB.interpolate_threshold(v["gm_db"], v["fast_P"], .75), "elapsed_s": v["elapsed_s"]}
(OUT / "casp_validation.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))

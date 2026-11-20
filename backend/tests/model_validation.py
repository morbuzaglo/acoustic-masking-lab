"""Reproducible research example: validation curves of the fast model, the scenario study (SYNTHETIC hammer and drill
against 9 masker scenes, flat and spectrally optimised), and a simulated-listener run of the 2AFC machinery.

Writes docs/validation/model_validation.json and docs/validation/scenario_results.json (used by the Word summary).
Runtime: ~15-30 minutes. Everything is seeded."""
import sys, json, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from aml import fastmodel as F, units as U, generators as G, service as S, experiments as E, optimize as O, spectra as SP

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "validation"
FS = 32000
t_all = time.time()

# ---------------------------------------------------------------- 1. tone-in-noise validation curves
n = FS
t = np.arange(n) / FS
N0 = U.P0 ** 2 * 10 ** 3.0


def noise(seed):
    return np.random.default_rng(seed).standard_normal(n) * np.sqrt(N0 * FS / 2)


def tone(f, dur):
    x = np.zeros(n); k = int(dur * FS); i0 = (n - k) // 2
    nr = min(int(0.01 * FS), k // 2)
    env = np.ones(k); env[:nr] = np.linspace(0, 1, nr); env[-nr:] = np.linspace(1, 0, nr)
    x[i0:i0 + k] = env * np.sin(2 * np.pi * f * t[i0:i0 + k]) * np.sqrt(2 * N0 * 10 ** 1.8)
    return x


val = {"eta": F.default_eta(fs=FS)}
freqs = [250, 500, 1000, 2000, 4000, 8000]
val["cr_vs_freq"] = {"f": freqs, "cr_db": [float(np.mean([18 + F.analyse(tone(f, .5), noise(s), FS).solve(.75, "target") for s in (1, 2, 3)])) for f in freqs]}
durs = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 0.9]
thr = [float(np.mean([F.analyse(tone(1000, d), noise(s), FS).solve(.75, "target") for s in (1, 2, 3)])) for d in durs]
val["duration"] = {"dur_s": durs, "threshold_rel_db": thr}
an = F.analyse(tone(1000, .5), noise(1), FS)
g = np.linspace(-12, 12, 49)
val["psychometric"] = {"gain_db": g.tolist(), "p": [an.p2afc(x) for x in g]}
# forward masking: 1 kHz probe 20 ms after a 200 ms 1 kHz-centred noise burst ends, as a function of gap
gaps = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2]
fm = []
nn = int(1.0 * FS); tt = np.arange(nn) / FS
rng = np.random.default_rng(5)
m = rng.standard_normal(nn) * 0.05
m[int(0.4 * FS):] = 0.0
for gp in gaps:
    pr = np.zeros(nn); i0 = int((0.4 + gp) * FS); L = int(0.02 * FS)
    pr[i0:i0 + L] = np.sin(2 * np.pi * 1000 * tt[i0:i0 + L]) * 0.01
    fm.append(float(F.analyse(pr, m, FS).solve(.75, "target")))
val["forward_masking"] = {"gap_s": gaps, "threshold_rel_db": fm}
(OUT / "model_validation.json").write_text(json.dumps(val, indent=1))
print("validation curves done", round(time.time() - t_all), "s", flush=True)

# ------------------------------------------------------------------ 2. scenario study
res = {}
for kind in ("hammer", "drill"):
    ws = S.Workspace(id=kind)
    ws.target_raw = G.synth_target(kind, 4.0, FS, 1, 60.0); ws.fs_raw = FS
    ws.synthetic_target = True
    ws.prepare()
    specs = S.default_specs()
    entry = {"target_LAeq": float(U.laeq(ws.target_event, FS)), "target_Lpeak": float(U.spl_from_pa_rms(np.max(np.abs(ws.target_event)))),
             "target_spectrum": SP.spectra_payload(ws.target_event, FS)["third_octave"], "criteria": {}}
    for pc in (0.6, 0.75):
        rows = S.compare_maskers(ws, specs, pc, 0.5, optimise=False)
        if kind == "hammer" and pc == 0.6:   # spectral optimisation is slow: three representative scenes only
            sub = S.compare_maskers(ws, [specs[0], specs[4], specs[3]], pc, 0.5, optimise=True)
            by = {r["name"]: r for r in sub}
            for r in rows:
                if r["name"] in by and by[r["name"]].get("optimised"):
                    r["optimised"] = by[r["name"]]["optimised"]
        entry["criteria"][str(pc)] = rows
        print(kind, pc, "done", round(time.time() - t_all), "s", flush=True)
    pred = S.predict_masker(ws, specs[0], 0.6, include_map=True)
    entry["map"] = {"fc": pred["map"]["fc"], "t": pred["map"]["t"], "snr_db": pred["map"]["snr_db"]}
    entry["curves"] = {sp["name"]: None for sp in specs}
    for sp in specs[:6]:
        p = S.predict_masker(ws, sp, 0.6, n_curve=41)
        entry["curves"][sp["name"]] = {"level": p["curve_masker"]["level"], "p": p["curve_masker"]["p"], "req": p["required_masker_LAeq"]}
    res[kind] = entry
(OUT / "scenario_results.json").write_text(json.dumps(res, indent=1, default=float))
print("scenario done", round(time.time() - t_all), "s", flush=True)

# --------------------------------------------- 3. simulated listener through the 2AFC machinery
ws = S.Workspace(id="sim"); ws.target_raw = G.synth_target("hammer", 3.0, FS, 1, 60.0); ws.fs_raw = FS; ws.prepare()
spec = S.default_specs()[0]
m = ws.render_masker(spec, 16.0, 7)
fac = E.StimulusFactory(ws.target_event, m, E.StimConfig(), 7)
true_thr, sigma = -26.0, 3.0
sim = {"true_threshold_db": true_thr, "sigma_db": sigma}
rng = np.random.default_rng(11)
sess = E.Session(id="sim1", participant="SIM", created=0.0, method="staircase", config={"rule": "2down1up", "n_tracks": 2, "n_reversals": 10, "starts": [-6.0, -12.0]}, levels=[], reps=0)
run = E.Runner(sess, fac)
while True:
    tr = run.next_trial()
    if tr is None:
        break
    rec = sess.trials[tr["index"]]
    ok = E.simulate_listener(rec["snr_db"], true_thr, sigma, 0.01, rng)
    run.answer(tr["index"], rec["answer"] if ok else ("A" if rec["answer"] == "B" else "B"))
sim["staircase"] = run.summary(0.7071)
sim["staircase_trials"] = [{"snr": t["snr_db"], "correct": t["correct"], "track": t["track"]} for t in sess.trials]
levels = [-38, -32, -26, -20, -14]
sess2 = E.Session(id="sim2", participant="SIM", created=0.0, method="constant", config={}, levels=levels, reps=20)
run2 = E.Runner(sess2, fac)
while True:
    tr = run2.next_trial()
    if tr is None:
        break
    rec = sess2.trials[tr["index"]]
    ok = E.simulate_listener(rec["snr_db"], true_thr, sigma, 0.01, rng)
    run2.answer(tr["index"], rec["answer"] if ok else ("A" if rec["answer"] == "B" else "B"))
sim["constant"] = run2.summary(0.75)
an = S._analysis_for(ws, m)
base = U.laeq(ws.target_event, FS) - U.laeq(m, FS)
grid = np.linspace(-45, -5, 41)
sim["model_curve"] = {"x": grid.tolist(), "p": [an.p2afc(x - base, 0.0) for x in grid]}
sim["model_threshold_075"] = float(base + an.solve(0.75, "target"))
(OUT / "simulated_listener.json").write_text(json.dumps(sim, indent=1, default=float))
print("ALL DONE", round(time.time() - t_all), "s", flush=True)

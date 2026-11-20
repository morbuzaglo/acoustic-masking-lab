"""Application service layer: workspaces, target preparation, masker rendering, prediction, optimisation.

No HTTP here; ``app.py`` is a thin wrapper. Everything is deterministic given the configuration (seeds).
"""
from __future__ import annotations
import json, pathlib, time, uuid
from dataclasses import dataclass, field
import numpy as np
from . import units as U, audio_io, spectra, generators as G, fastmodel as F, optimize as O, loudness as LD

FS = G.FS_DEFAULT
LIBRARY = None            # set by app.py (projects.Library) so saved scenes can find uploaded masker audio
MAX_ANALYSIS_S = 10.0
SEEDS_MC = (11, 23, 37)

NATURAL = {"wind", "crickets", "water", "rain", "leaves"}
SYNTHETIC = {"white", "pink", "brown"}


@dataclass
class Workspace:
    id: str
    name: str = "Untitled"
    target_raw: np.ndarray | None = None
    fs_raw: int = 0
    raw_meta: dict = field(default_factory=dict)
    source_label: str = ""
    synthetic_target: bool = False
    cal: audio_io.Calibration = field(default_factory=audio_io.Calibration)
    meas_distance: float = 7.0
    recv_distance: float = 7.0
    atmosphere: bool = True
    temperature_c: float = 20.0
    humidity: float = 70.0
    bg_raw: np.ndarray | None = None
    bg_fs: int = 0
    bg_segment: tuple | None = None       # (t0, t1) of the recording used as background-only
    bg_over: float = 1.0
    event: tuple | None = None            # (t0, t1) seconds
    custom_maskers: dict = field(default_factory=dict)   # id -> (samples Pa @FS, label)
    # derived
    target_full: np.ndarray | None = None      # Pa at receiver, FS, after calibration/bg/propagation
    target_event: np.ndarray | None = None
    warnings: list = field(default_factory=list)
    cal_gain: float = 1.0

    # ---------------------------------------------------------------- target
    def prepare(self):
        if self.target_raw is None:
            raise ValueError("no target loaded")
        self.warnings = []
        fs0 = self.fs_raw
        x = np.asarray(self.target_raw, float)
        x, g = audio_io.apply_calibration(x, fs0, self.cal)
        self.cal_gain = g
        x = x - np.mean(x)
        if np.max(np.abs(self.target_raw)) >= 0.999 and self.cal.mode != "pa_float":
            self.warnings.append("Samples reach digital full scale: the recording may be clipped.")
        # background removal (spectral subtraction of a noise-only segment or file)
        noise = None
        if self.bg_segment is not None:
            a, b = int(self.bg_segment[0] * fs0), int(self.bg_segment[1] * fs0)
            noise = x[a:b]
            nfs = fs0
        elif self.bg_raw is not None:
            noise, _ = audio_io.apply_calibration(np.asarray(self.bg_raw, float), self.bg_fs, self.cal)
            nfs = self.bg_fs
            if nfs != fs0:
                noise = audio_io.resample(noise, nfs, fs0)
        if noise is not None and len(noise) > 2048:
            from .spectra import third_octave_levels
            c = U.third_octave_centres(50, min(8000, fs0 / 2.5))
            margin = third_octave_levels(x, fs0, c) - third_octave_levels(noise, fs0, c)
            low = [float(f) for f, m in zip(c, margin) if np.isfinite(m) and m < 3]
            if low:
                self.warnings.append("Background within 3 dB of the recording in bands " + ", ".join(f"{v:g}" for v in low[:8]) +
                                     " Hz: the subtracted result is unreliable there (ISO 1996-2 corrections not applicable).")
            x = audio_io.spectral_subtract(x, fs0, noise, over=self.bg_over)
        if abs(self.recv_distance - self.meas_distance) > 1e-9:
            x = U.propagate(x, fs0, self.meas_distance, self.recv_distance, self.temperature_c, self.humidity, self.atmosphere)
        y = audio_io.resample(x, fs0, FS)
        self.target_full = y
        # analysis window
        dur = len(y) / FS
        if self.event is not None:
            t0, t1 = max(0.0, self.event[0]), min(dur, self.event[1])
        elif dur > MAX_ANALYSIS_S:
            tt, L = spectra.short_time_level(y, FS, 0.5, 0.25, "A")
            c = tt[int(np.argmax(L))]
            t0 = float(np.clip(c - MAX_ANALYSIS_S / 2, 0, dur - MAX_ANALYSIS_S)); t1 = t0 + MAX_ANALYSIS_S
            self.warnings.append(f"Recording is {dur:.0f} s long: the loudest {MAX_ANALYSIS_S:.0f} s window was selected automatically (set the event window to change).")
        else:
            t0, t1 = 0.0, dur
        if t1 - t0 > MAX_ANALYSIS_S + 1e-6:
            t1 = t0 + MAX_ANALYSIS_S
            self.warnings.append(f"Event window limited to {MAX_ANALYSIS_S:.0f} s.")
        self.event = (float(t0), float(t1))
        self.target_event = y[int(t0 * FS):int(t1 * FS)].copy()
        if len(self.target_event) < int(0.05 * FS):
            raise ValueError("event window shorter than 50 ms")
        return self.target_event

    def target_summary(self):
        y = self.target_full
        ev = self.target_event
        t, env_lo, env_hi = spectra.waveform_envelope(y, FS, 1800)
        tl, Ll = spectra.short_time_level(y, FS, 0.125, 0.0625, "A")
        S = spectra.spectra_payload(ev, FS)
        tt, ff, Ls = spectra.spectrogram_db(ev, FS, 0.032, 0.008, 12000)
        return {"fs_raw": self.fs_raw, "duration_s": len(y) / FS, "event": list(self.event), "cal": self.cal.to_dict(),
                "cal_gain": self.cal_gain, "distance": {"measured": self.meas_distance, "receiver": self.recv_distance,
                                                          "atmosphere": self.atmosphere, "T": self.temperature_c, "RH": self.humidity},
                "source": self.source_label, "synthetic": self.synthetic_target, "warnings": self.warnings,
                "waveform": {"t": t, "lo": env_lo, "hi": env_hi}, "level_time": {"t": tl.tolist(), "LA": np.round(Ll, 2).tolist()},
                "spectra": S, "spectrogram": {"t": np.round(tt + self.event[0], 4).tolist(), "f": np.round(ff, 1).tolist(),
                                              "L": np.round(Ls, 1).tolist()},
                "stats": {"LAeq_event": S["LAeq"], "Leq_event": S["Leq"], "Lpeak": S["Lpeak"],
                          "LAeq_full": U.laeq(y, FS), "LAFmax_approx": float(np.max(Ll))}}

    # --------------------------------------------------------------- maskers
    def render_masker(self, spec: dict, duration_s: float, seed: int = 1):
        """spec: {name, gain_db, components:[{type|custom,...}], seed?}. Returns Pa at FS (before gain_db)."""
        comps = spec.get("components") or []
        parts = []
        sig = np.zeros(int(round(duration_s * FS)))
        for k, c in enumerate(comps):
            if c.get("mute"):
                continue
            if c.get("type") == "custom":
                cid = c.get("custom_id")
                got = self.custom_maskers.get(cid) or (LIBRARY.get_audio(cid) if LIBRARY is not None else None)
                if got is None:
                    raise ValueError("custom masker audio not found (re-upload the WAV)")
                y, _ = got
                self.custom_maskers[cid] = got
                s = G.custom_masker(y, FS, FS, duration_s, level=c.get("level"), weighting=c.get("weighting", "A"), seed=seed)
            else:
                s = G.render_component(c, duration_s, FS, seed, k)
            sig += s
        sh = spec.get("shape")
        if sh:   # spectral shape found by the optimiser (absolute band gains for the scene at its stored levels)
            from . import optimize as _O
            sig = _O.shaping_filter(sig, FS, np.asarray(sh["centres"], float), np.asarray(sh["gains_db"], float))
        return sig * 10 ** (float(spec.get("gain_db", 0.0)) / 20)


def masker_metrics(x):
    m = LD.metrics(x, FS)
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}


# =========================================================== predictions
def _analysis_for(ws: Workspace, masker_sig, params=None):
    tgt = ws.target_event
    n = min(len(tgt), len(masker_sig))
    return F.analyse(tgt[:n], masker_sig[:n], FS, params or F.Params())


def predict_masker(ws: Workspace, spec: dict, p_crit=0.60, params=None, n_curve=61, include_map=False, offset_db=0.0):
    """Detectability of the workspace target in one masker scene (fast model, Monte-Carlo over masker seeds)."""
    dur = len(ws.target_event) / FS
    dur = max(dur, 1.0)
    tgt_laeq = U.laeq(ws.target_event, FS)
    levels, curves, snr_curves = [], [], []
    first = None
    base_laeq = None
    runs = []
    for seed in SEEDS_MC if spec_is_random(spec) else SEEDS_MC[:1]:
        m = ws.render_masker(spec, dur, seed)
        m_laeq = U.laeq(m, FS)
        if base_laeq is None:
            base_laeq = m_laeq
        an = _analysis_for(ws, m, params)
        if first is None:
            first = (an, m)
        gm = an.solve(p_crit, "masker")
        levels.append(m_laeq + gm if np.isfinite(gm) else np.nan)
        runs.append(an)
    # curves are centred on the required level so the criterion crossing is always inside the plot
    fin = [l - base_laeq for l in levels if np.isfinite(l)]
    centre = float(np.mean(fin)) if fin else 0.0
    grid = centre + np.linspace(-25, 25, n_curve)
    for an in runs:
        curves.append([an.p2afc(0.0, g) for g in grid])
        snr_curves.append([an.p2afc(-centre + g2, 0.0) for g2 in np.linspace(-25, 25, n_curve)])
    an, m = first
    unc = O.level_uncertainty(levels)
    req = unc["mean"] + offset_db if np.isfinite(unc["mean"]) else None
    P0 = an.p2afc(0.0, -200.0)
    out = {
        "name": spec.get("name", "masker"),
        "category": category(spec),
        "tgt_LAeq": tgt_laeq, "masker_LAeq_ref": base_laeq,
        "P_without_masker": P0,
        "required_masker_LAeq": req, "uncertainty": unc,
        "already_below_threshold": bool(P0 <= p_crit),
        "unreachable": bool((not np.isfinite(unc["mean"])) and not (P0 <= p_crit)),
        "P_at_plus80": float(runs[0].p2afc(0.0, 80.0)),
        "snr_at_threshold": (tgt_laeq - req) if req is not None else None,
        "curve_masker": {"level": (base_laeq + grid).tolist(), "p": np.mean(curves, axis=0).tolist(),
                         "p_lo": np.min(curves, axis=0).tolist(), "p_hi": np.max(curves, axis=0).tolist()},
        "curve_snr": {"snr": (tgt_laeq - base_laeq - centre + np.linspace(-25, 25, n_curve)).tolist(), "p": np.mean(snr_curves, axis=0).tolist()},
        "p_crit": p_crit,
    }
    if req is not None:
        gm_req = req - base_laeq - offset_db
        mm = masker_metrics(m * 10 ** (gm_req / 20))
        out["masker_metrics_at_required"] = mm
    if include_map:
        gm_show = float(spec.get("show_gain_db", 0.0))
        smap = an.snr_map_db(0.0, gm_show)
        out["map"] = _decimate_map(an.fc, an.t + 0.0, smap)
        out["channel_share"] = an.channel_contrib(0.0, gm_show).tolist()
        out["fc"] = an.fc.tolist()
        dp = an.dprime(0.0, gm_show, full=True)
        out["dprime_series"] = {"t": an.t.tolist(), "d2": dp["series"].tolist()}
        out["dprime"] = dp["d"]
        out["P_at_nominal"] = float(F.p2afc_from_dprime(dp["d"]))
    return out


def spec_is_random(spec):
    return any((c.get("type") not in ("custom",)) for c in (spec.get("components") or []))


def category(spec):
    types = {c.get("type") for c in spec.get("components", []) if not c.get("mute")}
    if not types:
        return "none"
    if types == {"custom"}:
        return "custom"
    if types <= NATURAL:
        return "natural"
    if types <= SYNTHETIC:
        return "synthetic"
    return "mixed"


def _decimate_map(fc, t, M, max_t=170):
    k = max(1, int(np.ceil(M.shape[1] / max_t)))
    n = (M.shape[1] // k) * k
    Mm = M[:, :n].reshape(M.shape[0], n // k, k).max(axis=2)
    tt = t[:n].reshape(-1, k).mean(axis=1)
    return {"fc": fc.tolist(), "t": tt.tolist(), "snr_db": np.round(np.clip(Mm, -60, 80), 1).tolist()}


def compare_maskers(ws: Workspace, specs: list[dict], p_crit=0.60, lam=0.5, optimise=True, params=None, offset_db=0.0):
    """Required level for each candidate masker (flat spectrum) and, optionally, the optimised spectral shape."""
    rows = []
    for spec in specs:
        r = predict_masker(ws, spec, p_crit, params, n_curve=31, offset_db=offset_db)
        row = {k: r[k] for k in ("name", "category", "required_masker_LAeq", "uncertainty", "already_below_threshold",
                                 "snr_at_threshold", "P_without_masker", "unreachable", "P_at_plus80")}
        row["metrics"] = r.get("masker_metrics_at_required")
        if optimise and r["required_masker_LAeq"] is not None and not r["already_below_threshold"]:
            dur = max(len(ws.target_event) / FS, 1.0)
            m = ws.render_masker(spec, dur, SEEDS_MC[0])
            sc = O.build_scene(ws.target_event, m, FS, params)
            opt = O.optimise_shape(sc, p_crit, lam)
            if opt.get("ok"):
                m_ref = U.laeq(m, FS)
                row["optimised"] = {"LAeq": opt["LAeq"], "centres": opt["centres"], "gains_db": opt["gains_db"],
                                    "saving_dBA": r["required_masker_LAeq"] - offset_db - opt["LAeq"] if True else None,
                                    "N_sone": opt["N_sone"], "flat_N_sone": opt["flat"]["N_sone"], "P2AFC": opt["P2AFC"]}
        rows.append(row)
    rows.sort(key=lambda r: (r["required_masker_LAeq"] if r["required_masker_LAeq"] is not None else 1e9))
    return rows


def default_specs():
    """Preset masker scenes offered in the UI (levels are *relative*: the whole scene is scaled by the solver)."""
    def one(t, name, **k):
        return {"name": name, "components": [{"type": t, "level": 40.0, "weighting": "A", **k}]}
    return [
        one("pink", "Pink noise"), one("white", "White noise"), one("brown", "Brown noise"),
        one("wind", "Wind with gusts"), one("water", "Flowing water"), one("rain", "Rain"),
        one("leaves", "Rustling leaves"), one("crickets", "Crickets chorus"),
        {"name": "Water + wind + leaves", "components": [
            {"type": "water", "level": 40.0, "weighting": "A"}, {"type": "wind", "level": 34.0, "weighting": "A"},
            {"type": "leaves", "level": 30.0, "weighting": "A"}]},
    ]

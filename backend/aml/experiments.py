"""Blinded 2AFC listening experiments: adaptive staircases, constant stimuli, psychometric fitting.

Definitions
  SNR      = A-weighted equivalent level of the target clip (its own duration) minus the A-weighted level
             of the masker, both physical receiver levels, dB.
  2AFC     = two intervals, both contain a masker excerpt, exactly one also contains the target; the
             listener names the interval with the target. The answer key never leaves the server.
  Rule     = n-down/1-up on SNR (1 up after every error, 1 down after n consecutive correct):
             2-down/1-up converges to 70.7 % correct, 3-down/1-up to 79.4 % (Levitt 1971).
  Presentation level = receiver level + ``level_offset_db``; a hard cap on the presented LAeq is applied
             by scaling target and masker together (the SNR is preserved).
"""
from __future__ import annotations
import json, time, uuid, pathlib
from dataclasses import dataclass, field, asdict
import numpy as np
from scipy import optimize, stats
from . import units as U
from . import generators as G
from . import audio_io

RULES = {"2down1up": (2, 0.7071), "3down1up": (3, 0.7937), "1down1up": (1, 0.5)}
HARD_CAP_DBA = 85.0           # never exceed, regardless of settings (hearing safety)
DEFAULT_CAP_DBA = 75.0


# --------------------------------------------------------------- staircase
@dataclass
class Staircase:
    start: float = 0.0                 # dB SNR
    rule: str = "2down1up"
    steps: tuple = (6.0, 6.0, 3.0, 3.0, 1.5)   # step size by reversal index (last repeats)
    n_reversals: int = 10
    use_last: int = 6
    lo: float = -45.0
    hi: float = 30.0
    value: float = None
    reversals: list = field(default_factory=list)
    history: list = field(default_factory=list)   # (value, correct)
    _run: int = 0
    _dir: int = 0

    def __post_init__(self):
        if self.value is None:
            self.value = self.start

    @property
    def n_down(self):
        return RULES[self.rule][0]

    def step_size(self):
        i = min(len(self.reversals), len(self.steps) - 1)
        return self.steps[i]

    def update(self, correct: bool):
        self.history.append((self.value, bool(correct)))
        move = 0
        if correct:
            self._run += 1
            if self._run >= self.n_down:
                move = -1
                self._run = 0
        else:
            move = +1
            self._run = 0
        if move != 0:
            if self._dir != 0 and move != self._dir:
                self.reversals.append(self.value)
            self._dir = move
            self.value = float(np.clip(self.value + move * self.step_size(), self.lo, self.hi))

    @property
    def finished(self):
        return len(self.reversals) >= self.n_reversals

    def threshold(self):
        r = self.reversals[-self.use_last:] if len(self.reversals) >= 2 else [h[0] for h in self.history[-6:]]
        if not r:
            return float("nan"), float("nan")
        return float(np.mean(r)), float(np.std(r, ddof=1)) if len(r) > 1 else float("nan")


# ------------------------------------------------------- psychometric fit
def _pf(x, mu, sigma, gamma, lam):
    return gamma + (1 - gamma - lam) * stats.norm.cdf((x - mu) / sigma)


def fit_psychometric(snr, correct, gamma=0.5, fit_lapse=False, p_crit=0.75, n_boot=200, seed=1):
    """ML fit of P(x) = gamma + (1-gamma-lambda) Phi((x-mu)/sigma). Returns dict with mu, sigma, threshold at p_crit
    and a parametric-bootstrap 95 % interval. Needs data at >= 3 distinct levels."""
    x = np.asarray(snr, float); y = np.asarray(correct, float)
    lv = np.unique(x)
    if len(lv) < 3 or len(x) < 12:
        return {"ok": False, "reason": "need >= 12 trials at >= 3 distinct levels"}
    n = np.array([np.sum(x == l) for l in lv]); k = np.array([np.sum(y[x == l]) for l in lv])

    def nll(p, lam_fixed=0.01):
        mu, ls = p[0], p[1]
        lam = p[2] if fit_lapse else lam_fixed
        pr = np.clip(_pf(lv, mu, np.exp(ls), gamma, lam), 1e-6, 1 - 1e-6)
        pen = 0.0
        if fit_lapse:
            pen = 50.0 * max(0.0, lam - 0.06) ** 2
        return -np.sum(k * np.log(pr) + (n - k) * np.log(1 - pr)) + pen

    best = None
    for mu0 in np.linspace(lv.min(), lv.max(), 5):
        p0 = [mu0, np.log(3.0)] + ([0.02] if fit_lapse else [])
        r = optimize.minimize(nll, p0, method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 2000})
        if best is None or r.fun < best.fun:
            best = r
    mu, sigma = float(best.x[0]), float(np.exp(best.x[1]))
    lam = float(best.x[2]) if fit_lapse else 0.01

    def thr(mu, sigma, lam):
        q = (p_crit - gamma) / (1 - gamma - lam)
        q = min(max(q, 1e-6), 1 - 1e-6)
        return mu + sigma * stats.norm.ppf(q)

    th = thr(mu, sigma, lam)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        kb = rng.binomial(n, np.clip(_pf(lv, mu, sigma, gamma, lam), 0, 1))

        def nllb(p):
            pr = np.clip(_pf(lv, p[0], np.exp(p[1]), gamma, lam), 1e-6, 1 - 1e-6)
            return -np.sum(kb * np.log(pr) + (n - kb) * np.log(1 - pr))
        rb = optimize.minimize(nllb, [mu, np.log(sigma)], method="Nelder-Mead", options={"maxiter": 600})
        boots.append(thr(rb.x[0], np.exp(rb.x[1]), lam))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    xs = np.linspace(min(lv) - 6, max(lv) + 6, 120)
    return {"ok": True, "mu": mu, "sigma": sigma, "gamma": gamma, "lapse": lam, "threshold": float(th), "p_crit": p_crit,
            "ci95": [float(lo), float(hi)], "levels": lv.tolist(), "n": n.tolist(), "k": k.tolist(),
            "curve": {"x": xs.tolist(), "p": _pf(xs, mu, sigma, gamma, lam).tolist()}, "nll": float(best.fun)}


# ------------------------------------------------- stimulus construction
@dataclass
class StimConfig:
    fs: int = 32000
    interval_s: float = 2.0
    lead_s: float = 0.35               # masker-only lead-in before the target clip
    level_offset_db: float = 0.0       # presentation level - physical receiver level
    cap_dba: float = DEFAULT_CAP_DBA
    spl_at_full_scale_db: float = 100.0   # headphone sensitivity: dB SPL (RMS) of a full-scale sine
    calibrated: bool = False
    gap_s: float = 0.6


class StimulusFactory:
    """Pre-renders a masker pool once; builds A/B intervals per trial deterministically from the session seed."""

    def __init__(self, target_pa, masker_pa, cfg: StimConfig, seed=1):
        self.cfg = cfg
        self.seed = int(seed)
        self.target = np.asarray(target_pa, float)
        self.masker = np.asarray(masker_pa, float)
        fs = cfg.fs
        self.target_laeq = U.laeq(self.target, fs)
        self.masker_laeq = U.laeq(self.masker, fs)
        self.dur = max(cfg.interval_s, len(self.target) / fs + 2 * cfg.lead_s)
        self.n = int(round(self.dur * fs))
        if len(self.masker) < 2 * self.n + fs:
            raise ValueError(f"masker too short: need >= {2 * self.dur + 1:.1f} s, have {len(self.masker) / fs:.1f} s")

    def _segment(self, rng, avoid=None):
        for _ in range(50):
            s = int(rng.integers(0, len(self.masker) - self.n))
            if avoid is None or abs(s - avoid) > self.n:
                return s, self.masker[s:s + self.n].copy()
        return 0, self.masker[: self.n].copy()

    def present_gain(self, snr_db):
        """Return (linear gain applied to both signals, presented LAeq of the louder component, capped?)."""
        # physical levels at the receiver: masker at its own LAeq, target at masker + snr
        L_m = self.masker_laeq + self.cfg.level_offset_db
        L_t = L_m + snr_db - 0.0
        top = max(L_m, L_t)
        cap = min(self.cfg.cap_dba, HARD_CAP_DBA)
        red = max(0.0, top - cap)
        return 10 ** (-red / 20), top - red, red > 0

    def build_trial(self, trial_index, snr_db):
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, 77, int(trial_index)]))
        fs = self.cfg.fs
        t_first = int(rng.integers(0, 2))             # 0 -> target in A, 1 -> target in B
        s1, m1 = self._segment(rng)
        s2, m2 = self._segment(rng, avoid=s1)
        tg = self.target * 10 ** ((self.masker_laeq + snr_db - self.target_laeq) / 20)
        tg_iv = np.zeros(self.n)
        i0 = int(self.cfg.lead_s * fs)
        tg_iv[i0:i0 + len(tg)] = tg[: self.n - i0]
        off = 10 ** (self.cfg.level_offset_db / 20)
        g, top, capped = self.present_gain(snr_db)
        A = (m1 + (tg_iv if t_first == 0 else 0)) * off * g
        B = (m2 + (tg_iv if t_first == 1 else 0)) * off * g
        return {"A": A, "B": B, "answer": "A" if t_first == 0 else "B", "presented_top_dba": top, "capped": capped}

    def to_wav(self, x):
        """Pa -> digital samples using the headphone calibration; short fades; peak limiter at -1 dBFS."""
        pa_peak_fs = U.pa_rms_from_spl(self.cfg.spl_at_full_scale_db) * np.sqrt(2)
        d = np.asarray(x, float) / pa_peak_fs
        nf = int(0.03 * self.cfg.fs)
        w = np.ones(len(d)); w[:nf] = np.linspace(0, 1, nf); w[-nf:] = np.linspace(1, 0, nf)
        d *= w
        pk = np.max(np.abs(d))
        limited = pk > 0.89
        if limited:
            d *= 0.89 / pk
        return audio_io.write_wav_bytes(d.astype(np.float32), self.cfg.fs, "PCM_24"), bool(limited)


# ----------------------------------------------------------------- session
@dataclass
class Session:
    id: str
    participant: str
    created: float
    config: dict
    method: str                    # 'staircase' or 'constant'
    tracks: list = field(default_factory=list)     # list of staircase states (dict)
    trials: list = field(default_factory=list)     # all trials, each a dict
    levels: list = field(default_factory=list)     # constant-stimuli levels
    reps: int = 0
    done: bool = False
    notes: str = ""

    def to_json(self):
        return json.dumps(asdict(self), indent=1, default=float)


class Runner:
    """Server-side state machine around a Session + StimulusFactory (answers never sent to the client)."""

    def __init__(self, session: Session, factory: StimulusFactory):
        self.s = session
        self.f = factory
        self.rule = session.config.get("rule", "2down1up")
        self.n_tracks = int(session.config.get("n_tracks", 2))
        self.pending = {}
        self.rng = np.random.default_rng(np.random.SeedSequence([factory.seed, 5]))
        if session.method == "staircase":
            starts = session.config.get("starts") or [session.config.get("start", 6.0), session.config.get("start", 6.0) - 4]
            self.stairs = [Staircase(start=float(starts[i % len(starts)]), rule=self.rule,
                                     n_reversals=int(session.config.get("n_reversals", 10))) for i in range(self.n_tracks)]
            self.order = []
        else:
            lv = list(session.levels)
            self.queue = [l for _ in range(session.reps) for l in lv]
            self.rng.shuffle(self.queue)
            self.qi = 0

    # -- trial flow
    def next_trial(self):
        if self.s.done:
            return None
        if self.s.method == "staircase":
            active = [i for i, st in enumerate(self.stairs) if not st.finished]
            if not active:
                self.s.done = True
                return None
            ti = int(self.rng.choice(active))          # interleave tracks to avoid anticipation
            snr = self.stairs[ti].value
            track = ti
        else:
            if self.qi >= len(self.queue):
                self.s.done = True
                return None
            snr = float(self.queue[self.qi]); self.qi += 1; track = -1
        idx = len(self.s.trials)
        tr = self.f.build_trial(idx, snr)
        rec = {"index": idx, "track": track, "snr_db": float(snr), "answer": tr["answer"], "response": None,
               "correct": None, "t_presented": time.time(), "rt_s": None, "presented_top_dba": tr["presented_top_dba"],
               "capped": tr["capped"]}
        self.s.trials.append(rec)
        wavs = {}
        limited_any = False
        for k in ("A", "B"):
            wavs[k], lim = self.f.to_wav(tr[k])
            limited_any |= lim
        rec["limited"] = limited_any
        self.pending[idx] = wavs
        return {"index": idx, "n_done": idx, "capped": tr["capped"], "presented_top_dba": tr["presented_top_dba"], "limited": limited_any}

    def stim(self, idx, which):
        return self.pending[idx][which]

    def answer(self, idx, response):
        rec = self.s.trials[idx]
        if rec["response"] is not None:
            return rec["correct"]
        rec["response"] = response
        rec["correct"] = bool(response == rec["answer"])
        rec["rt_s"] = time.time() - rec["t_presented"]
        if self.s.method == "staircase" and rec["track"] >= 0:
            self.stairs[rec["track"]].update(rec["correct"])
            self.s.tracks = [{"history": st.history, "reversals": st.reversals, "finished": st.finished} for st in self.stairs]
            if all(st.finished for st in self.stairs):
                self.s.done = True
        elif self.s.method == "constant" and self.qi >= len(self.queue):
            self.s.done = True
        self.pending.pop(idx, None)
        return rec["correct"]

    # -- analysis
    def summary(self, p_crit=None):
        tr = [t for t in self.s.trials if t["correct"] is not None]
        out = {"n_trials": len(tr), "pc": float(np.mean([t["correct"] for t in tr])) if tr else None}
        if self.s.method == "staircase":
            th = [st.threshold() for st in self.stairs]
            vals = [t[0] for t in th if np.isfinite(t[0])]
            out["track_thresholds"] = [t[0] for t in th]
            out["staircase_threshold"] = float(np.mean(vals)) if vals else None
            out["staircase_sd"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else None
            out["converges_to"] = RULES[self.rule][1]
        pc = p_crit if p_crit is not None else (RULES[self.rule][1] if self.s.method == "staircase" else 0.75)
        out["psychometric"] = fit_psychometric([t["snr_db"] for t in tr], [t["correct"] for t in tr], p_crit=pc)
        return out


def save_session(s: Session, folder: pathlib.Path):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{s.id}.json").write_text(s.to_json(), encoding="utf-8")


def load_session(path):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return Session(**d)


def simulate_listener(snr_db, threshold_db, slope_sigma=3.0, lapse=0.01, rng=None):
    """Ideal-observer-like synthetic participant used by tests and the demo: P = 0.5 + (0.5-lapse) Phi((x-mu)/sigma)."""
    rng = rng or np.random.default_rng()
    p = 0.5 + (0.5 - lapse) * stats.norm.cdf((snr_db - threshold_db) / slope_sigma)
    return rng.random() < p
